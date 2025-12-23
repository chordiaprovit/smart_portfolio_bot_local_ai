import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../state/app_state.dart';

class TopRisksScreen extends StatefulWidget {
  final bool autoCompute;
  const TopRisksScreen({super.key, this.autoCompute = false});

  @override
  State<TopRisksScreen> createState() => _TopRisksScreenState();
}

class _TopRisksScreenState extends State<TopRisksScreen> {
  bool _started = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();

    if (_started) return;
    _started = true;

    if (widget.autoCompute) {
      // Run after first frame so navigation feels smooth
      WidgetsBinding.instance.addPostFrameCallback((_) async {
        final state = context.read<AppState>();
        await state.computeHealth();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();

    return Scaffold(
      appBar: AppBar(title: const Text("Top Risks")),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text("What needs attention", style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 6),
            Text(
              "These are rule-based insights (not trading advice).",
              style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: 16),

            if (state.loading) ...[
              const Center(child: CircularProgressIndicator()),
              const SizedBox(height: 12),
              Text(
                "Analyzing your portfolio…",
                style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
              ),
              const Spacer(),
            ] else ...[
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text("Top risks", style: TextStyle(fontWeight: FontWeight.w700)),
                      const SizedBox(height: 10),
                      if (state.health == null)
                        Text(
                          "No health report yet. Tap “Compute” below.",
                          style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
                        )
                      else
                        ...state.health!.topRisks.map((r) => Padding(
                              padding: const EdgeInsets.only(bottom: 8),
                              child: Text("• $r"),
                            )),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 12),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text("Correlation insights", style: TextStyle(fontWeight: FontWeight.w700)),
                      const SizedBox(height: 10),
                      if (state.insights == null)
                        Text(
                          "No insights yet. Tap “Compute” below.",
                          style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
                        )
                      else
                        ...state.insights!.correlationWarnings.map((w) => Padding(
                              padding: const EdgeInsets.only(bottom: 8),
                              child: Text("• $w"),
                            )),
                    ],
                  ),
                ),
              ),

              if (state.error != null) ...[
                const SizedBox(height: 12),
                Text(state.error!, style: const TextStyle(color: Colors.red)),
              ],

              const Spacer(),
            ],

            SizedBox(
              width: double.infinity,
              height: 54,
              child: FilledButton(
                onPressed: state.loading ? null : () => context.read<AppState>().computeHealth(),
                child: Text(state.loading ? "Computing..." : "Compute / Refresh"),
              ),
            ),
            const SizedBox(height: 10),
            Center(
              child: Text(
                "NOT A TRADING APP • A DECISION-CONFIDENCE APP",
                style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
