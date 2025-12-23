import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';
import '../widgets/score_gauge.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();

    return Scaffold(
      appBar: AppBar(title: const Text("Your Portfolio")),
      body: Padding(
        padding: const EdgeInsets.all(20),
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
                style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
              )
            else ...[
              Text(
                state.starter!.name,
                style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
              ),
              const SizedBox(height: 12),
              ...state.starter!.allocations.map((a) => ListTile(
                    contentPadding: EdgeInsets.zero,
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
                  )),
            ],

            const SizedBox(height: 20),

            SizedBox(
              width: double.infinity,
              height: 54,
              child: FilledButton(
                onPressed: state.loading ? null : () => context.read<AppState>().computeHealth(),
                child: Text(state.loading ? "Computing..." : "Compute Health Score"),
              ),
            ),

            const SizedBox(height: 24),

            if (state.health != null) ...[
              Center(child: ScoreGauge(score: state.health!.score, label: "Health Score")),
              const SizedBox(height: 12),
              Text("Top risks:", style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 6),
              ...state.health!.topRisks.map((r) => Text("• $r")),
            ],

            if (state.error != null) ...[
              const SizedBox(height: 12),
              Text(state.error!, style: const TextStyle(color: Colors.red)),
            ],
          ],
        ),
      ),
    );
  }
}
