import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import '../models/models.dart';
import '../services/portfolio_service.dart';

class AppState extends ChangeNotifier {
  final PortfolioService service;
  AppState(this.service) {
    _loadEtfSymbols();
  }

  // Onboarding
  String investmentStyle = "Long-term";
  String assetInterest = "ETFs";
  String focus = "Growth";
  String involvement = "Set & forget";
  String ageRange = "36-50";

  // Editable portfolio
  List<HoldingIn> holdings = [
    HoldingIn(ticker: "VOO", weight: 0.5, type: "etf"),
    HoldingIn(ticker: "QQQ", weight: 0.3, type: "etf"),
    HoldingIn(ticker: "AAPL", weight: 0.2, type: "stock"),
  ];

  Set<String> _etfSymbols = {};
  bool loading = false;
  String? error;

  HealthResponse? health;
  InsightsResponse? insights;
  StarterPortfolioResponse? starter;

  Future<void> _loadEtfSymbols() async {
    try {
      final data = await rootBundle.loadString('assets/etf_symbols.txt');
      _etfSymbols = data.split('\n')
          .map((s) => s.trim().toUpperCase())
          .where((s) => s.isNotEmpty)
          .toSet();
    } catch (e) {
      // If loading fails, continue with empty set
      _etfSymbols = {};
    }
  }

  String _getHoldingType(String ticker) {
    return _etfSymbols.contains(ticker.toUpperCase()) ? 'etf' : 'stock';
  }

  Future<void> computeHealth() async {
    loading = true; error = null; notifyListeners();
    try {
      health = await service.getHealth(holdings: holdings, focus: focus, ageRange: ageRange);
      insights = await service.getInsights(holdings: holdings, focus: focus, ageRange: ageRange);
    } catch (e) {
      error = e.toString();
    } finally {
      loading = false; notifyListeners();
    }
  }

  Future<void> loadStarter() async {
    loading = true; error = null; notifyListeners();
    try {
      starter = await service.getStarterPortfolio(
        investmentStyle: investmentStyle,
        assetInterest: assetInterest,
        focus: focus,
        involvement: involvement,
        ageRange: ageRange,
      );
      // Initialize holdings from starter portfolio and compute health
      if (starter != null) {
        holdings = starter!.allocations.map((a) => HoldingIn(ticker: a.ticker, weight: a.weight, type: a.type)).toList();
        health = await service.getHealth(holdings: holdings, focus: focus, ageRange: ageRange);
        insights = await service.getInsights(holdings: holdings, focus: focus, ageRange: ageRange);
      }
    } catch (e) {
      error = e.toString();
    } finally {
      loading = false; notifyListeners();
    }
  }

  void setHoldingWeight(int index, double w) {
    final h = holdings[index];
    holdings[index] = HoldingIn(ticker: h.ticker, weight: w, type: h.type);
    notifyListeners();
  }

  void addHolding(String ticker) {
    final exists = holdings.any((h) => h.ticker.toUpperCase() == ticker.toUpperCase());
    if (exists) return;
    final type = _getHoldingType(ticker);
    holdings = [...holdings, HoldingIn(ticker: ticker.toUpperCase(), weight: 0.05, type: type)];
    notifyListeners();
  }

  void removeHolding(int index) {
    holdings = [...holdings]..removeAt(index);
    notifyListeners();
  }

  void equalizeHoldings() {
  if (holdings.isEmpty) return;
  final n = holdings.length;
  final raw = 1.0 / n;
  // round to 4 decimals
  final w = double.parse(raw.toStringAsFixed(4));
  holdings = holdings.map((h) => HoldingIn(ticker: h.ticker, weight: w, type: h.type)).toList();
  notifyListeners();
 }

  void initializeHoldingsFromStarter() {
    if (starter == null) return;
    holdings = starter!.allocations.map((a) => HoldingIn(ticker: a.ticker, weight: a.weight, type: a.type)).toList();
    notifyListeners();
  }

  void updateStarterFromHoldings() {
    if (holdings.isEmpty) return;
    
    // Create allocations with names from the service
    final allocations = holdings.map((h) {
      final name = service.getTickerName(h.ticker);
      return StarterAllocation(
        ticker: h.ticker,
        type: h.type,
        name: name,
        weight: h.weight,
        reason: 'User-adjusted holding',
      );
    }).toList();
    
    // Generate name similar to the original starter portfolio
    final name = '$investmentStyle • $focus • $assetInterest • $involvement • $ageRange';
    
    // Create notes
    final notes = [
      'Custom portfolio adjusted by user.',
      'This is a starting point, not trading advice. Adjust anytime.',
    ];
    
    starter = StarterPortfolioResponse(
      asOf: DateTime.now().toIso8601String().split('T').first,
      name: name,
      allocations: allocations,
      notes: notes,
    );
    
    notifyListeners();
  }
}
