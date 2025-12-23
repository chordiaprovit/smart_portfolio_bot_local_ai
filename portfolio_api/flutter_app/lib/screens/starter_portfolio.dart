import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';
import '../widgets/score_gauge.dart';
import 'diagnosis_adjust.dart';
import 'top_risks.dart';

class StarterPortfolioScreen extends StatelessWidget {
  const StarterPortfolioScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();

    return Scaffold(
      appBar: AppBar(
        title: const Text("Your Starter Portfolio"),
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
        child: state.starter == null
            ? _EmptyStarter(
                loading: state.loading,
                onLoad: () => context.read<AppState>().loadStarter(),
              )
            : Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    state.starter!.name,
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 6),
                  Text(
                    "A simple starting point — adjustable anytime.",
                    style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
                  ),
                  const SizedBox(height: 18),

                  // Optional: show last computed health if available
                  if (state.health != null) ...[
                    Center(child: ScoreGauge(score: state.health!.score, label: "Health Score")),
                    const SizedBox(height: 14),
                  ],

                  Expanded(
                    child: ListView(
                      children: [
                        ...state.starter!.allocations.map(
                          (a) => Card(
                            child: ListTile(
                              title: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    children: [
                                      Text(a.ticker),
                                      const Spacer(),
                                      Text("${(a.weight * 100).toStringAsFixed(0)}%"),
                                    ],
                                  ),
                                  Text(a.name, style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant)),
                                ],
                              ),
                              subtitle: Text(a.reason),
                              trailing: Text(a.type.toUpperCase(),
                                  style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
                            ),
                          ),
                        ),
                        const SizedBox(height: 8),
                        ...state.starter!.notes.map(
                          (n) => Padding(
                            padding: const EdgeInsets.only(top: 6),
                            child: Text("• $n",
                                style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
                          ),
                        ),
                      ],
                    ),
                  ),

                  const SizedBox(height: 12),

                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton(
                          onPressed: () {
                            Navigator.push(
                              context,
                              MaterialPageRoute(builder: (_) => const TopRisksScreen()),
                            );
                          },
                          child: const Text("See Risks"),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: FilledButton(
                          onPressed: () {
                            // Initialize holdings from starter portfolio before adjusting
                            context.read<AppState>().initializeHoldingsFromStarter();
                            Navigator.push(
                              context,
                              MaterialPageRoute(builder: (_) => const DiagnosisAdjustScreen()),
                            );
                          },
                          child: const Text("Adjust Portfolio"),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
      ),
    );
  }
}

class _EmptyStarter extends StatelessWidget {
  final bool loading;
  final VoidCallback onLoad;

  const _EmptyStarter({required this.loading, required this.onLoad});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            "No starter portfolio loaded yet.",
            style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
          ),
          const SizedBox(height: 12),
          FilledButton(
            onPressed: loading ? null : onLoad,
            child: Text(loading ? "Loading..." : "Load Starter Portfolio"),
          ),
        ],
      ),
    );
  }
}
