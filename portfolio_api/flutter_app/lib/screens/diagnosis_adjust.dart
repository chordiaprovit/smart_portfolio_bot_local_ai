import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';
import '../models/models.dart';
import '../widgets/score_gauge.dart';
import 'top_risks.dart';

class DiagnosisAdjustScreen extends StatefulWidget {
  const DiagnosisAdjustScreen({super.key});

  @override
  State<DiagnosisAdjustScreen> createState() => _DiagnosisAdjustScreenState();
}

class _DiagnosisAdjustScreenState extends State<DiagnosisAdjustScreen> {
  final TextEditingController _search = TextEditingController();
  List<String> _suggestions = [];
  bool _searching = false;

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _doSearch(AppState state, String q) async {
    if (q.trim().isEmpty) {
      setState(() => _suggestions = []);
      return;
    }
    setState(() => _searching = true);
    try {
      final res = await state.service.searchTickers(q.trim());
      if (!mounted) return;
      setState(() => _suggestions = res);
    } catch (_) {
      if (!mounted) return;
      setState(() => _suggestions = []);
    } finally {
      if (!mounted) return;
      setState(() => _searching = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();

    return Scaffold(
      appBar: AppBar(
        title: const Text("Portfolio Health Diagnosis"),
        actions: [
          IconButton(
            tooltip: "Top Risks",
            onPressed: () {
              Navigator.push(context, MaterialPageRoute(builder: (_) => const TopRisksScreen()));
            },
            icon: const Icon(Icons.warning_amber_rounded),
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          children: [
            if (state.health != null) ...[
              Center(child: ScoreGauge(score: state.health!.score, label: "Health Score")),
              const SizedBox(height: 10),
              Text(
                "Adjust weights to see how the score changes.",
                style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
              ),
              const SizedBox(height: 12),
            ],

            // Add ticker search
            Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: TextField(
                            controller: _search,
                            decoration: InputDecoration(
                              hintText: "Add ticker (e.g., VOO, AAPL, QQQ)",
                              prefixIcon: const Icon(Icons.search),
                              suffixIcon: _searching
                                  ? const Padding(
                                      padding: EdgeInsets.all(12),
                                      child: SizedBox(width: 18, height: 18, child: CircularProgressIndicator()),
                                    )
                                  : (_search.text.isEmpty
                                      ? null
                                      : IconButton(
                                          icon: const Icon(Icons.clear),
                                          onPressed: () {
                                            _search.clear();
                                            setState(() => _suggestions = []);
                                          },
                                        )),
                              border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                            ),
                            onChanged: (v) => _doSearch(state, v),
                          ),
                        ),
                      ],
                    ),
                    if (_suggestions.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      SizedBox(
                        height: 140,
                        child: ListView.builder(
                          itemCount: _suggestions.length,
                          itemBuilder: (context, i) {
                            final t = _suggestions[i];
                            return ListTile(
                              dense: true,
                              title: Text(t),
                              trailing: const Icon(Icons.add_circle_outline),
                              onTap: () {
                                context.read<AppState>().addHolding(t);
                                _search.clear();
                                setState(() => _suggestions = []);
                              },
                            );
                          },
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),

            const SizedBox(height: 12),

            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () => context.read<AppState>().equalizeHoldings(),
                    icon: const Icon(Icons.balance),
                    label: const Text("Equalize Weights"),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FilledButton.icon(
                    onPressed: state.loading ? null : () => context.read<AppState>().computeHealth(),
                    icon: const Icon(Icons.refresh),
                    label: Text(state.loading ? "..." : "Recompute"),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),

            // Holdings list with sliders
            Expanded(
              child: ListView.builder(
                itemCount: state.holdings.length,
                itemBuilder: (context, index) {
                  final h = state.holdings[index];
                  return _HoldingCard(
                    holding: h,
                    onWeightChanged: (v) => context.read<AppState>().setHoldingWeight(index, v),
                    onRemove: () => context.read<AppState>().removeHolding(index),
                  );
                },
              ),
            ),

            const SizedBox(height: 12),

            SizedBox(
              width: double.infinity,
              height: 54,
              child: FilledButton(
                onPressed: state.loading ? null : () async {
                  final appState = context.read<AppState>();
                  await appState.computeHealth();
                  // Update starter portfolio with current holdings
                  appState.updateStarterFromHoldings();
                },
                child: Text(state.loading ? "Computing..." : "Recompute Health & Update Portfolio"),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _HoldingCard extends StatelessWidget {
  final HoldingIn holding;
  final ValueChanged<double> onWeightChanged;
  final VoidCallback onRemove;

  const _HoldingCard({
    required this.holding,
    required this.onWeightChanged,
    required this.onRemove,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    holding.ticker,
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                  ),
                ),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text("${(holding.weight * 100).toStringAsFixed(1)}%"),
                    Text(
                      holding.type.toUpperCase(),
                      style: TextStyle(
                        fontSize: 10,
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
                IconButton(
                  tooltip: "Remove",
                  onPressed: onRemove,
                  icon: const Icon(Icons.delete_outline),
                ),
              ],
            ),
            Slider(
              value: holding.weight.clamp(0.0, 1.0),
              onChanged: onWeightChanged,
              min: 0,
              max: 1,
            ),
            Text(
              "Tip: weights don’t need to sum to 100% — we normalize automatically.",
              style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant),
            ),
          ],
        ),
      ),
    );
  }
}
