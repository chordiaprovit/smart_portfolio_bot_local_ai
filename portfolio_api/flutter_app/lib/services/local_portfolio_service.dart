import 'dart:convert';
import 'dart:math';

import 'package:flutter/services.dart' show rootBundle;

import '../models/models.dart';
import 'portfolio_service.dart';

/// Local (no-endpoint) implementation of [PortfolioService].
///
/// Mirrors the rules in your Python `app.py`, but runs entirely on-device using
/// `assets/analytics_pack.json`.
class LocalPortfolioService implements PortfolioService {
  final String packAssetPath;

  LocalPortfolioService({this.packAssetPath = 'assets/analytics_pack.json'});

  bool _loaded = false;
  String? _asOf;
  late Map<String, dynamic> _tickers; // ticker -> metrics
  late Map<String, dynamic> _corrTop; // ticker -> [{t,c}, ...]

  Future<void> _ensureLoaded() async {
    if (_loaded) return;
    final raw = await rootBundle.loadString(packAssetPath);
    final j = jsonDecode(raw) as Map<String, dynamic>;
    _asOf = j['asOf'] as String?;
    _tickers = Map<String, dynamic>.from(j['tickers'] as Map);
    _corrTop = Map<String, dynamic>.from(j['correlationTop'] as Map);
    _loaded = true;
  }

  // ------------------------- helpers (mirrors app.py) -------------------------

  List<MapEntry<String, double>> _normalizeWeights(List<HoldingIn> holdings) {
    final cleaned = <MapEntry<String, double>>[];
    for (final h in holdings) {
      final t = h.ticker.trim().toUpperCase();
      final w = h.weight;
      if (w > 0) cleaned.add(MapEntry(t, w));
    }
    if (cleaned.isEmpty) {
      throw Exception('No holdings with weight > 0 provided.');
    }

    final weights = cleaned.map((e) => e.value).toList();
    final total = weights.fold<double>(0, (a, b) => a + b);
    final mx = weights.reduce(max);

    // If user likely entered percentages (e.g., 60, 20, 20)
    var norm = cleaned;
    if (mx > 1.0 || total > 1.5) {
      norm = cleaned.map((e) => MapEntry(e.key, e.value / 100.0)).toList();
    }

    final total2 = norm.fold<double>(0, (a, b) => a + b.value);
    if (total2 <= 0) {
      throw Exception('Total weight must be > 0.');
    }
    return norm.map((e) => MapEntry(e.key, e.value / total2)).toList();
  }

  double _gini(List<double> weights) {
    final w = weights.map((x) => max(0.0, x)).toList();
    final sum = w.fold<double>(0, (a, b) => a + b);
    if (w.isEmpty || sum == 0) return 1.0;
    w.sort();
    final n = w.length;
    var cum = 0.0;
    for (var i = 0; i < n; i++) {
      cum += (i + 1) * w[i];
    }
    return (2 * cum) / (n * sum) - (n + 1) / n;
  }

  double _clamp01(double x) => max(0.0, min(1.0, x));

  int _linearScore(double value, {required double goodAtOrBelow, required double badAtOrAbove}) {
    if (value <= goodAtOrBelow) return 25;
    if (value >= badAtOrAbove) return 0;
    final frac = (value - goodAtOrBelow) / (badAtOrAbove - goodAtOrBelow);
    return (25 * (1.0 - frac)).round();
  }

  double _getMetric(String t, String key, double fallback) {
    final m = _tickers[t];
    if (m is Map) {
      final v = m[key];
      if (v is num) return v.toDouble();
      if (v is String) return double.tryParse(v) ?? fallback;
    }
    return fallback;
  }

  (int, String) _goalAlignmentScore(List<MapEntry<String, double>> wByTicker, String focus) {
    var wCagr = 0.0;
    var wVol = 0.0;
    var wTrend = 0.0;
    for (final e in wByTicker) {
      final t = e.key;
      final w = e.value;
      wCagr += w * _getMetric(t, 'cagr', 0.0);
      wVol += w * _getMetric(t, 'vol', 0.25);
      wTrend += w * _getMetric(t, 'trend', 0.0);
    }

    if (focus == 'Growth') {
      final score = (25 * _clamp01((wCagr - 0.00) / 0.12)).round();
      return (score, 'Weighted 1Y growth proxy (CAGR) ≈ ${(wCagr * 100).toStringAsFixed(1)}%.');
    }

    if (focus == 'Stability') {
      final score = _linearScore(wVol, goodAtOrBelow: 0.12, badAtOrAbove: 0.35);
      return (score, 'Weighted volatility proxy ≈ ${(wVol * 100).toStringAsFixed(1)}% (lower is more stable).');
    }

    if (focus == 'Dividend') {
      final volScore = _linearScore(wVol, goodAtOrBelow: 0.14, badAtOrAbove: 0.40);
      final cagrScore = (25 * _clamp01((wCagr + 0.02) / 0.10)).round();
      final score = (0.6 * volScore + 0.4 * cagrScore).round();
      return (
        score,
        'No yield data in v1; using proxies. Vol ≈ ${(wVol * 100).toStringAsFixed(1)}%, growth proxy ≈ ${(wCagr * 100).toStringAsFixed(1)}%.',
      );
    }

    // Active returns
    final trendScore = (25 * _clamp01((wTrend - 0.0000) / 0.0015)).round();
    final volPenalty = _linearScore(wVol, goodAtOrBelow: 0.18, badAtOrAbove: 0.55);
    final score = (0.6 * trendScore + 0.4 * volPenalty).round();
    return (
      score,
      'Using trend+vol proxies. Trend ≈ ${wTrend.toStringAsFixed(5)} (log-slope/day), vol ≈ ${(wVol * 100).toStringAsFixed(1)}%.',
    );
  }

  (int, String, Map<String, double>) _sectorBalanceScore(List<MapEntry<String, double>> wByTicker) {
    final sectorW = <String, double>{};
    for (final e in wByTicker) {
      final t = e.key;
      final w = e.value;
      String sector = 'unknown';
      final m = _tickers[t];
      if (m is Map && m['sector'] != null) {
        sector = (m['sector'] as String).trim();
      }
      sectorW[sector] = (sectorW[sector] ?? 0.0) + w;
    }
    final maxEntry = sectorW.entries.reduce((a, b) => a.value >= b.value ? a : b);
    final score = _linearScore(maxEntry.value, goodAtOrBelow: 0.20, badAtOrAbove: 0.45);
    final expl = "Largest sector is '${maxEntry.key}' at ${(maxEntry.value * 100).toStringAsFixed(1)}% (<=20% is ideal for full points).";
    return (score, expl, sectorW);
  }

  // ------------------------- starter portfolio helpers -------------------------

  String _pick(List<String> options) {
    for (final t in options) {
      if (_tickers.containsKey(t)) return t;
    }
    return options.first;
  }

  String _getName(String ticker) {
    return _tickers[ticker]?['name'] as String? ?? ticker;
  }

  String _getType(String ticker) {
    return _tickers[ticker]?['type'] as String? ?? 'unknown';
  }

  List<_Alloc> _normalizeAllocs(List<_Alloc> allocs) {
    final s = allocs.fold<double>(0, (a, b) => a + b.weight);
    if (s <= 0) return allocs;
    return allocs.map((a) => a.copyWith(weight: a.weight / s)).toList();
  }

  List<_Alloc> _splitOverweightAllocations({
    required List<_Alloc> allocs,
    required double cap,
    required Map<String, List<String>> replacementPools,
  }) {
    var norm = _normalizeAllocs(allocs);

    List<String> subsFor(String t) {
      final subs = replacementPools[t] ?? const <String>[];
      return subs.where((x) => _tickers.containsKey(x)).toList();
    }

    void merge(List<_Alloc> out, _Alloc a) {
      final idx = out.indexWhere((x) => x.ticker == a.ticker && x.type == a.type);
      if (idx >= 0) {
        out[idx] = out[idx].copyWith(weight: out[idx].weight + a.weight);
      } else {
        out.add(a);
      }
    }

    final out = <_Alloc>[];
    for (final a in norm) {
      if (a.weight <= cap) {
        merge(out, a);
        continue;
      }

      // Split overweight allocation into <=cap chunks using substitute pool.
      var n = (a.weight / cap).floor() + ((a.weight % cap) > 1e-12 ? 1 : 0);
      n = max(2, n);
      final base = a.ticker;
      final subs = subsFor(base);
      var chosen = <String>[base, ...subs.take(max(0, n - 1))];

      var parts = chosen.length;
      var chunk = a.weight / parts;
      if (chunk > cap) {
        parts = (a.weight / cap).floor() + 1;
        final pool = chosen.isNotEmpty ? chosen : <String>[base];
        final expanded = <String>[];
        for (var i = 0; i < parts; i++) {
          expanded.add(pool[i % pool.length]);
        }
        chosen = expanded;
        parts = chosen.length;
        chunk = a.weight / parts;
      }

      for (final t in chosen) {
        merge(
          out,
          _Alloc(
            ticker: t,
            type: a.type,
            name: a.name,
            weight: chunk,
            reason: '${a.reason} (split for balance)',
          ),
        );
      }
    }

    // Round + renormalize (matches Python intent)
    var rounded = _normalizeAllocs(out)
        .map((a) => a.copyWith(weight: double.parse(a.weight.toStringAsFixed(4))))
        .toList();
    rounded = _normalizeAllocs(rounded)
        .map((a) => a.copyWith(weight: double.parse(a.weight.toStringAsFixed(4))))
        .toList();
    return rounded;
  }

  // ------------------------- PortfolioService -------------------------

  @override
  Future<List<String>> searchTickers(String query) async {
    await _ensureLoaded();
    final q = query.trim().toUpperCase();
    if (q.isEmpty) return [];
    final matches = _tickers.keys.where((t) => t.contains(q)).toList()..sort();
    return matches.take(10).toList();
  }

  @override
  String getTickerName(String ticker) {
    return _getName(ticker);
  }

  @override
  Future<HealthResponse> getHealth({
    required List<HoldingIn> holdings,
    required String focus,
    String? ageRange,
  }) async {
    await _ensureLoaded();
    final wByTicker = _normalizeWeights(holdings);

    final unknown = wByTicker.where((e) => !_tickers.containsKey(e.key)).map((e) => e.key).toList();
    if (unknown.isNotEmpty) {
      throw Exception('Unknown tickers (not in analytics_pack): ${unknown.take(20).toList()}');
    }

    final weights = wByTicker.map((e) => e.value).toList();
    final top = wByTicker.reduce((a, b) => a.value >= b.value ? a : b);
    final topTicker = top.key;
    final topW = top.value;

    final g = _gini(weights);
    final allocScore = (25 * (1.0 - _clamp01(g))).round();
    final concScore = _linearScore(topW, goodAtOrBelow: 0.10, badAtOrAbove: 0.50);

    final (sectorScore, sectorExpl, sectorW) = _sectorBalanceScore(wByTicker);
    final (goalScore, goalExpl) = _goalAlignmentScore(wByTicker, focus);

    var total = allocScore + concScore + sectorScore + goalScore;
    total = max(0, min(100, total));

    final risks = <String>[];
    if (topW >= 0.30) {
      risks.add('Top holding $topTicker is ${(topW * 100).toStringAsFixed(1)}% of your portfolio (concentration risk).');
    } else if (topW >= 0.20) {
      risks.add('Top holding $topTicker is ${(topW * 100).toStringAsFixed(1)}% — consider trimming if you want more balance.');
    }

    final maxSector = sectorW.entries.reduce((a, b) => a.value >= b.value ? a : b);
    if (maxSector.value >= 0.45) {
      risks.add("Sector overexposure: '${maxSector.key}' is ${(maxSector.value * 100).toStringAsFixed(1)}% (high)." );
    } else if (maxSector.value >= 0.30) {
      risks.add("Sector tilt: '${maxSector.key}' is ${(maxSector.value * 100).toStringAsFixed(1)}% (moderate)." );
    }

    if (allocScore <= 10) {
      risks.add('Your allocations are uneven across holdings (low allocation equality).');
    }
    if (risks.isEmpty) {
      risks.add('No major red flags detected based on v1 rules.');
    }

    final explain = <String, String>{
      'allocationEquality': 'Gini(weights) ≈ ${g.toStringAsFixed(2)} → $allocScore/25.',
      'concentration': 'Top holding $topTicker = ${(topW * 100).toStringAsFixed(1)}% → $concScore/25.',
      'sectorBalance': '$sectorExpl → $sectorScore/25.',
      'goalAlignment': '$goalExpl → $goalScore/25.',
    };

    return HealthResponse(
      asOf: _asOf,
      score: total,
      subScores: SubScores(
        allocationEquality: allocScore,
        concentration: concScore,
        sectorBalance: sectorScore,
        goalAlignment: goalScore,
      ),
      topRisks: risks.take(5).toList(),
      explainability: explain,
    );
  }

  @override
  Future<InsightsResponse> getInsights({
    required List<HoldingIn> holdings,
    required String focus,
    String? ageRange,
  }) async {
    await _ensureLoaded();
    final wByTicker = _normalizeWeights(holdings);
    final tickers = wByTicker.map((e) => e.key).toList();

    final unknown = tickers.where((t) => !_tickers.containsKey(t)).toList();
    if (unknown.isNotEmpty) {
      throw Exception('Unknown tickers: ${unknown.take(20).toList()}');
    }

    if (_corrTop.isEmpty) {
      return InsightsResponse(
        asOf: _asOf,
        correlationWarnings: [
          'Correlation insights aren’t available (no correlationTop data in analytics pack).'
        ],
      );
    }

    final pairs = <String, double>{}; // "A|B" -> corr

    for (final a in tickers) {
      final items = _corrTop[a];
      if (items is! List) continue;
      for (final item in items) {
        if (item is! Map) continue;
        final bRaw = item['t'] ?? item['ticker'] ?? item['symbol'];
        if (bRaw == null) continue;
        final b = bRaw.toString().toUpperCase();

        final cRaw = item['c'] ?? item['corr'] ?? item['value'];
        final c = (cRaw is num) ? cRaw.toDouble() : double.tryParse(cRaw?.toString() ?? '');
        if (c == null) continue;

        if (tickers.contains(b) && a != b) {
          final sorted = ([a, b]..sort());
          final key = '${sorted[0]}|${sorted[1]}';
          pairs[key] = max(pairs[key] ?? -1e9, c);
        }
      }
    }

    final sortedPairs = pairs.entries.toList()..sort((x, y) => y.value.compareTo(x.value));
    final topPairs = sortedPairs.take(10).toList();

    final warnings = <String>[];
    for (final p in topPairs.take(5)) {
      final parts = p.key.split('|');
      final a = parts[0];
      final b = parts[1];
      final c = p.value;
      if (c >= 0.90) {
        warnings.add('$a and $b move very similarly (corr ≈ ${c.toStringAsFixed(2)}). Diversification may be lower than it looks.');
      } else if (c >= 0.80) {
        warnings.add('$a and $b are highly correlated (corr ≈ ${c.toStringAsFixed(2)}).');
      } else if (c >= 0.70) {
        warnings.add('$a and $b are moderately correlated (corr ≈ ${c.toStringAsFixed(2)}).');
      }
    }

    if (warnings.isEmpty) {
      warnings.add('No strong correlation overlaps detected among your selected holdings (based on stored top correlations).');
    }

    return InsightsResponse(asOf: _asOf, correlationWarnings: warnings);
  }

  @override
  Future<StarterPortfolioResponse> getStarterPortfolio({
    required String investmentStyle,
    required String assetInterest,
    required String focus,
    required String involvement,
    String? ageRange,
  }) async {
    await _ensureLoaded();

    final age = (ageRange == null || ageRange.isEmpty) ? '36-50' : ageRange;

    // Common building blocks
    final usCore = _pick(['VTI', 'VOO', 'SPY', 'IVV']);
    final usGrowth = _pick(['QQQ', 'QQQM']);
    final intlCore = _pick(['VEA', 'IEFA']);
    final bondsCore = _pick(['BND', 'AGG', 'IEF']);
    final longBonds = _pick(['TLT', 'EDV', 'IEF']);
    final shortBonds = _pick(['SHY', 'VGSH', 'BIL']);

    // Age-based equity/bond targets
    double equityTarget;
    double bondTarget;
    if (age == '20-35') {
      equityTarget = 0.90;
      bondTarget = 0.10;
    } else if (age == '36-50') {
      equityTarget = 0.80;
      bondTarget = 0.20;
    } else if (age == '51-65') {
      equityTarget = 0.65;
      bondTarget = 0.35;
    } else {
      equityTarget = 0.55;
      bondTarget = 0.45;
    }

    // Style nudges
    if (investmentStyle == 'Conservative') {
      bondTarget = min(0.65, bondTarget + 0.10);
      equityTarget = 1.0 - bondTarget;
    } else if (investmentStyle == 'Active') {
      equityTarget = min(0.95, equityTarget + 0.05);
      bondTarget = 1.0 - equityTarget;
    }

    final wantSimple = involvement == 'Set & forget';
    final wantMid = involvement == 'Monthly';
    final wantMore = involvement == 'Tweak';

    final allocations = <StarterAllocation>[];
    final notes = <String>[];

    // CASE 1: “I don’t know”
    if (assetInterest == 'I don’t know') {
      final wUs = equityTarget * 0.70;
      final wIntl = equityTarget * 0.30;
      final wBonds = bondTarget;
      allocations.addAll([
        StarterAllocation(ticker: usCore, type: _getType(usCore), name: _getName(usCore), weight: double.parse(wUs.toStringAsFixed(4)), reason: 'Broad US market core (simple + diversified).'),
        StarterAllocation(ticker: intlCore, type: _getType(intlCore), name: _getName(intlCore), weight: double.parse(wIntl.toStringAsFixed(4)), reason: 'International diversification (reduces single-country risk).'),
        StarterAllocation(ticker: bondsCore, type: _getType(bondsCore), name: _getName(bondsCore), weight: double.parse(wBonds.toStringAsFixed(4)), reason: 'Bond buffer for stability (helps reduce drawdowns).'),
      ]);
      notes.addAll([
        'Kept intentionally simple: US + International + Bonds.',
        'Good default if you’re not sure where to start.',
        'This is a starting point, not trading advice. Adjust anytime.',
      ]);
    }

    // CASE 2: Bonds
    else if (assetInterest == 'Bonds') {
      final equity = min(0.35, equityTarget);
      final bonds = 1.0 - equity;
      if (wantSimple) {
        allocations.addAll([
          StarterAllocation(ticker: bondsCore, type: _getType(bondsCore), name: _getName(bondsCore), weight: double.parse(bonds.toStringAsFixed(4)), reason: 'Core bond exposure.'),
          StarterAllocation(ticker: usCore, type: _getType(usCore), name: _getName(usCore), weight: double.parse(equity.toStringAsFixed(4)), reason: 'Small equity core for growth.'),
        ]);
      } else {
        allocations.addAll([
          StarterAllocation(ticker: shortBonds, type: _getType(shortBonds), name: _getName(shortBonds), weight: double.parse((bonds * 0.40).toStringAsFixed(4)), reason: 'Short-term bonds (typically less volatile).'),
          StarterAllocation(ticker: bondsCore, type: _getType(bondsCore), name: _getName(bondsCore), weight: double.parse((bonds * 0.40).toStringAsFixed(4)), reason: 'Intermediate bond core.'),
          StarterAllocation(ticker: longBonds, type: _getType(longBonds), name: _getName(longBonds), weight: double.parse((bonds * 0.20).toStringAsFixed(4)), reason: 'Longer duration bonds (more rate sensitivity).'),
          StarterAllocation(ticker: usCore, type: _getType(usCore), name: _getName(usCore), weight: double.parse(equity.toStringAsFixed(4)), reason: 'Small equity core for growth.'),
        ]);
      }
      notes.addAll([
        'Bond-heavy starter portfolio (stability-focused).',
        'Equity allocation is intentionally small.',
        'This is a starting point, not trading advice. Adjust anytime.',
      ]);
    }

    // CASE 3: Stocks
    else if (assetInterest == 'Stocks') {
      final stockCandidates = [
        _pick(['AAPL']),
        _pick(['MSFT']),
        _pick(['JNJ']),
        _pick(['JPM']),
        _pick(['XOM']),
        _pick(['PG']),
        _pick(['COST', 'WMT']),
        _pick(['UNH']),
      ];
      final k = wantSimple ? 4 : (wantMid ? 6 : 8);
      final picks = stockCandidates.take(k).toList();
      final each = 1.0 / picks.length;
      for (final t in picks) {
        allocations.add(StarterAllocation(ticker: t, type: _getType(t), name: _getName(t), weight: double.parse(each.toStringAsFixed(4)), reason: 'Stock pick for diversified portfolio.'));
      }
      notes.addAll([
        'Stock-focused starter portfolio with individual stock picks.',
        'Replace with your own holdings anytime.',
        'This is a starting point, not trading advice. Adjust anytime.',
      ]);
    }

    // CASE 4: ETFs
    else if (assetInterest == 'ETFs') {
      final equity = equityTarget;
      final bonds = bondTarget;

      late double wUs;
      late double wGrowth;
      late double wIntl;
      if (focus == 'Growth') {
        wUs = equity * 0.55;
        wGrowth = equity * 0.35;
        wIntl = equity * 0.10;
      } else if (focus == 'Stability') {
        wUs = equity * 0.70;
        wGrowth = equity * 0.10;
        wIntl = equity * 0.20;
      } else if (focus == 'Dividend') {
        wUs = equity * 0.75;
        wGrowth = equity * 0.05;
        wIntl = equity * 0.20;
      } else {
        wUs = equity * 0.40;
        wGrowth = equity * 0.45;
        wIntl = equity * 0.15;
      }

      if (wantSimple) {
        allocations.addAll([
          StarterAllocation(ticker: usCore, type: _getType(usCore), name: _getName(usCore), weight: double.parse((wUs + wGrowth).toStringAsFixed(4)), reason: 'US equity ETF core.'),
          StarterAllocation(ticker: intlCore, type: _getType(intlCore), name: _getName(intlCore), weight: double.parse(wIntl.toStringAsFixed(4)), reason: 'International equity ETF.'),
          StarterAllocation(ticker: bondsCore, type: _getType(bondsCore), name: _getName(bondsCore), weight: double.parse(bonds.toStringAsFixed(4)), reason: 'Bond ETF for stability.'),
        ]);
        notes.add('Simple ETF-only starter portfolio.');
      } else if (wantMid) {
        allocations.addAll([
          StarterAllocation(ticker: usCore, type: _getType(usCore), name: _getName(usCore), weight: double.parse(wUs.toStringAsFixed(4)), reason: 'Broad US market ETF.'),
          StarterAllocation(ticker: usGrowth, type: _getType(usGrowth), name: _getName(usGrowth), weight: double.parse(wGrowth.toStringAsFixed(4)), reason: 'Growth-focused ETF.'),
          StarterAllocation(ticker: intlCore, type: _getType(intlCore), name: _getName(intlCore), weight: double.parse(wIntl.toStringAsFixed(4)), reason: 'International market ETF.'),
          StarterAllocation(ticker: bondsCore, type: _getType(bondsCore), name: _getName(bondsCore), weight: double.parse(bonds.toStringAsFixed(4)), reason: 'Bond ETF for stability.'),
        ]);
        notes.add('Balanced ETF-only starter portfolio.');
      } else {
        allocations.addAll([
          StarterAllocation(ticker: usCore, type: _getType(usCore), name: _getName(usCore), weight: double.parse(wUs.toStringAsFixed(4)), reason: 'Broad US market ETF.'),
          StarterAllocation(ticker: usGrowth, type: _getType(usGrowth), name: _getName(usGrowth), weight: double.parse(wGrowth.toStringAsFixed(4)), reason: 'Growth-focused ETF.'),
          StarterAllocation(ticker: intlCore, type: _getType(intlCore), name: _getName(intlCore), weight: double.parse(wIntl.toStringAsFixed(4)), reason: 'International market ETF.'),
          StarterAllocation(ticker: shortBonds, type: _getType(shortBonds), name: _getName(shortBonds), weight: double.parse((bonds * 0.40).toStringAsFixed(4)), reason: 'Short-term bond ETF.'),
          StarterAllocation(ticker: longBonds, type: _getType(longBonds), name: _getName(longBonds), weight: double.parse((bonds * 0.60).toStringAsFixed(4)), reason: 'Longer-term bond ETF.'),
        ]);
        notes.add('Granular ETF-only starter portfolio.');
      }
      notes.add('This is a starting point, not trading advice. Adjust anytime.');
    }

    // CASE 5: All of the above
    else if (assetInterest == 'All of the above') {
      final equity = equityTarget;
      final bonds = bondTarget;

      late double etfCoreShare;
      late double stockShare;
      late int stockCount;
      late int etfCount;
      late int bondCount;
      if (wantSimple) {
        etfCoreShare = 0.75;
        stockShare = 0.25;
        stockCount = 2;
        etfCount = 1;
        bondCount = 1;
      } else if (wantMid) {
        etfCoreShare = 0.65;
        stockShare = 0.35;
        stockCount = 3;
        etfCount = 2;
        bondCount = 1;
      } else {
        etfCoreShare = 0.55;
        stockShare = 0.45;
        stockCount = 5;
        etfCount = 3;
        bondCount = 2;
      }

      var etfs = <String>[];
      if (focus == 'Growth' || focus == 'Active returns') {
        etfs = [usCore, usGrowth, intlCore];
      } else if (focus == 'Stability') {
        etfs = [usCore, intlCore, bondsCore];
      } else {
        etfs = [usCore, intlCore, bondsCore];
      }
      etfs = etfs.take(etfCount).toList();

      final stockCandidates = [
        _pick(['AAPL']),
        _pick(['MSFT']),
        _pick(['JNJ']),
        _pick(['JPM']),
        _pick(['PG']),
        _pick(['XOM']),
        _pick(['COST', 'WMT']),
        _pick(['UNH']),
      ];
      final stocks = stockCandidates.take(stockCount).toList();

      var bondEtfs = <String>[bondsCore];
      if (bondCount == 2) bondEtfs = [shortBonds, longBonds];

      final wEtfsTotal = equity * etfCoreShare;
      final wStocksTotal = equity * stockShare;
      final wBondsTotal = bonds;

      final eachEtf = etfs.isEmpty ? 0.0 : wEtfsTotal / etfs.length;
      final eachStock = stocks.isEmpty ? 0.0 : wStocksTotal / stocks.length;
      final eachBond = bondEtfs.isEmpty ? 0.0 : wBondsTotal / bondEtfs.length;

      for (final t in etfs) {
        allocations.add(StarterAllocation(ticker: t, type: _getType(t), name: _getName(t), weight: double.parse(eachEtf.toStringAsFixed(4)), reason: 'ETF core for broad diversification.'));
      }
      for (final t in stocks) {
        allocations.add(StarterAllocation(ticker: t, type: _getType(t), name: _getName(t), weight: double.parse(eachStock.toStringAsFixed(4)), reason: 'Stock slice for added sector variety.'));
      }
      for (final t in bondEtfs) {
        allocations.add(StarterAllocation(ticker: t, type: _getType(t), name: _getName(t), weight: double.parse(eachBond.toStringAsFixed(4)), reason: 'Bond buffer to improve stability.'));
      }

      notes.addAll([
        'Balanced mix of ETFs + Stocks + Bonds (diversified baseline).',
        'Holdings count changes based on how hands-on you want to be.',
        'This is a starting point, not trading advice. Adjust anytime.',
      ]);
    }

    // CASE 6: Default (mix)
    else {
      final equity = equityTarget;
      final bonds = bondTarget;

      late double etfCoreShare;
      late double stockShare;
      late int stockCount;
      late int etfCount;
      late int bondCount;
      if (wantSimple) {
        etfCoreShare = 0.75;
        stockShare = 0.25;
        stockCount = 2;
        etfCount = 1;
        bondCount = 1;
      } else if (wantMid) {
        etfCoreShare = 0.65;
        stockShare = 0.35;
        stockCount = 3;
        etfCount = 2;
        bondCount = 1;
      } else {
        etfCoreShare = 0.55;
        stockShare = 0.45;
        stockCount = 5;
        etfCount = 3;
        bondCount = 2;
      }

      var etfs = <String>[];
      if (focus == 'Growth' || focus == 'Active returns') {
        etfs = [usCore, usGrowth, intlCore];
      } else if (focus == 'Stability') {
        etfs = [usCore, intlCore, bondsCore];
      } else {
        etfs = [usCore, intlCore, bondsCore];
      }
      etfs = etfs.take(etfCount).toList();

      final stockCandidates = [
        _pick(['AAPL']),
        _pick(['MSFT']),
        _pick(['JNJ']),
        _pick(['JPM']),
        _pick(['PG']),
        _pick(['XOM']),
        _pick(['COST', 'WMT']),
        _pick(['UNH']),
      ];
      final stocks = stockCandidates.take(stockCount).toList();

      var bondEtfs = <String>[bondsCore];
      if (bondCount == 2) bondEtfs = [shortBonds, longBonds];

      final wEtfsTotal = equity * etfCoreShare;
      final wStocksTotal = equity * stockShare;
      final wBondsTotal = bonds;

      final eachEtf = etfs.isEmpty ? 0.0 : wEtfsTotal / etfs.length;
      final eachStock = stocks.isEmpty ? 0.0 : wStocksTotal / stocks.length;
      final eachBond = bondEtfs.isEmpty ? 0.0 : wBondsTotal / bondEtfs.length;

      for (final t in etfs) {
        allocations.add(StarterAllocation(ticker: t, type: _getType(t), name: _getName(t), weight: double.parse(eachEtf.toStringAsFixed(4)), reason: 'ETF core for broad diversification.'));
      }
      for (final t in stocks) {
        allocations.add(StarterAllocation(ticker: t, type: _getType(t), name: _getName(t), weight: double.parse(eachStock.toStringAsFixed(4)), reason: 'Stock slice for added sector variety.'));
      }
      for (final t in bondEtfs) {
        allocations.add(StarterAllocation(ticker: t, type: _getType(t), name: _getName(t), weight: double.parse(eachBond.toStringAsFixed(4)), reason: 'Bond buffer to improve stability.'));
      }

      notes.addAll([
        'Balanced mix of ETFs + Stocks + Bonds (diversified baseline).',
        'Holdings count changes based on how hands-on you want to be.',
        'This is a starting point, not trading advice. Adjust anytime.',
      ]);
    }

    // Normalize weights
    final total = allocations.fold<double>(0, (a, b) => a + b.weight);
    if (total > 0) {
      for (var i = 0; i < allocations.length; i++) {
        final a = allocations[i];
        allocations[i] = StarterAllocation(
          ticker: a.ticker,
          type: a.type,
          name: a.name,
          weight: double.parse((a.weight / total).toStringAsFixed(4)),
          reason: a.reason,
        );
      }
    }

    final name = '$investmentStyle • $focus • $assetInterest • $involvement • $age';

    // Split overweight allocations (cap 0.12)
    final replacementPools = <String, List<String>>{
      'BND': ['AGG', 'IEF', 'TLT', 'SHY'],
      'AGG': ['BND', 'IEF', 'TLT', 'SHY'],
      'IEF': ['BND', 'AGG', 'TLT', 'SHY'],
      'VTI': ['VOO', 'SPY', 'IVV'],
      'VOO': ['VTI', 'SPY', 'IVV'],
      'SPY': ['VTI', 'VOO', 'IVV'],
      'IVV': ['VTI', 'VOO', 'SPY'],
      'QQQ': ['QQQM', 'VUG', 'XLK'],
      'QQQM': ['QQQ', 'VUG', 'XLK'],
      'VEA': ['IEFA'],
      'IEFA': ['VEA'],
    };

    final allocObjs = allocations
        .map((a) => _Alloc(ticker: a.ticker, type: a.type, name: a.name, weight: a.weight, reason: a.reason))
        .toList();
    final split = _splitOverweightAllocations(allocs: allocObjs, cap: 0.12, replacementPools: replacementPools);
    final finalAllocs = split
        .map((a) => StarterAllocation(ticker: a.ticker, type: a.type, name: a.name, weight: a.weight, reason: a.reason))
        .toList();

    return StarterPortfolioResponse(
      asOf: _asOf,
      name: name,
      allocations: finalAllocs,
      notes: notes,
    );
  }
}

class _Alloc {
  final String ticker;
  final String type;
  final String name;
  final double weight;
  final String reason;

  const _Alloc({required this.ticker, required this.type, required this.name, required this.weight, required this.reason});

  _Alloc copyWith({String? ticker, String? type, String? name, double? weight, String? reason}) {
    return _Alloc(
      ticker: ticker ?? this.ticker,
      type: type ?? this.type,
      name: name ?? this.name,
      weight: weight ?? this.weight,
      reason: reason ?? this.reason,
    );
  }
}
