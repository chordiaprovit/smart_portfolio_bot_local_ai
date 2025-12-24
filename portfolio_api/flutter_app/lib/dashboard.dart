import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';
import '../widgets/score_gauge.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final cs = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(title: const Text("Your Portfolio")),

      // ✅ BODY = scrollable content + fixed bottom panel
      body: SafeArea(
        child: Column(
          children: [
            // --------------------------
            // 1) Scrollable content area
            // --------------------------
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      "Starter portfolio",
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    const SizedBox(height: 8),

                    if (state.starter == null)
                      Text(
                        "No starter portfolio loaded yet.",
                        style: TextStyle(color: cs.onSurfaceVariant),
                      )
                    else ...[
                      Text(
                        state.starter!.name,
                        style: TextStyle(color: cs.onSurfaceVariant),
                      ),
                      const SizedBox(height: 12),
                      ...state.starter!.allocations.map(
                        (a) => ListTile(
                          contentPadding: EdgeInsets.zero,
                          title: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Expanded(
                                    child: Text(
                                      a.ticker,
                                      overflow: TextOverflow.ellipsis,
                                      style: Theme.of(context).textTheme.titleMedium,
                                    ),
                                  ),
                                  const SizedBox(width: 12),
                                  Text(
                                    "${(a.weight * 100).toStringAsFixed(0)}%",
                                    style: Theme.of(context).textTheme.titleMedium,
                                  ),
                                ],
                              ),
                              const SizedBox(height: 2),
                              Text(
                                a.name,
                                style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant),
                              ),
                            ],
                          ),
                          subtitle: Padding(
                            padding: const EdgeInsets.only(top: 6),
                            child: Text(a.reason),
                          ),
                        ),
                      ),
                    ],

                    const SizedBox(height: 20),

                    SizedBox(
                      width: double.infinity,
                      height: 54,
                      child: FilledButton(
                        onPressed: state.loading
                            ? null
                            : () => context.read<AppState>().computeHealth(),
                        child: Text(state.loading ? "Computing..." : "Compute Health Score"),
                      ),
                    ),

                    if (state.loading) ...[
                      const SizedBox(height: 12),
                      const LinearProgressIndicator(),
                    ],

                    const SizedBox(height: 24),

                    if (state.health != null) ...[
                      Center(
                        child: ScoreGauge(
                          score: state.health!.score,
                          label: "Health Score",
                        ),
                      ),
                      const SizedBox(height: 12),
                      Text("Top risks:", style: Theme.of(context).textTheme.titleMedium),
                      const SizedBox(height: 6),
                      ...state.health!.topRisks.map(
                        (r) => Padding(
                          padding: const EdgeInsets.only(bottom: 4),
                          child: Text("• $r"),
                        ),
                      ),
                    ],

                    if (state.error != null) ...[
                      const SizedBox(height: 12),
                      Text(state.error!, style: const TextStyle(color: Colors.red)),
                    ],
                  ],
                ),
              ),
            ),

            // --------------------------
            // 2) Fixed bottom panel
            // --------------------------
            Container(
              decoration: BoxDecoration(
                color: Theme.of(context).scaffoldBackgroundColor,
                border: Border(top: BorderSide(color: cs.outlineVariant)),
              ),
              padding: const EdgeInsets.fromLTRB(16, 10, 16, 12),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  // ✅ Static action buttons (move them up slightly with padding)
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: state.health == null
                              ? null
                              : () {
                                  // TODO: navigate to top risks screen
                                  // Navigator.push(context, MaterialPageRoute(builder: (_) => const TopRisksScreen()));
                                },
                          icon: const Icon(Icons.warning_amber_rounded),
                          label: const Text("See Risks"),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: FilledButton.icon(
                          onPressed: state.health == null
                              ? null
                              : () {
                                  // TODO: navigate to adjust portfolio screen
                                  // Navigator.push(context, MaterialPageRoute(builder: (_) => const DiagnosisAdjustScreen()));
                                },
                          icon: const Icon(Icons.tune),
                          label: const Text("Adjust"),
                        ),
                      ),
                    ],
                  ),

                  const SizedBox(height: 6),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
