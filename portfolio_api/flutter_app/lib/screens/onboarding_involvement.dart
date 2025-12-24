import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';
import '../widgets/pill_button.dart';
import '../screens/starter_portfolio.dart';

class OnboardingInvolvementScreen extends StatelessWidget {
  const OnboardingInvolvementScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();

    return Scaffold(
      appBar: AppBar(
        title: const Text("Involvement Level"),
      ),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 12),

            Text(
              "How hands-on do you want to be?",
              style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
            ),

            const SizedBox(height: 28),

            PillButton(
              text: "Set & forget",
              selected: state.involvement == "Set & forget",
              onTap: () {
                state.involvement = "Set & forget";
                state.notifyListeners();
              },
            ),
            const SizedBox(height: 16),

            PillButton(
              text: "Monthly check-in",
              selected: state.involvement == "Monthly",
              onTap: () {
                state.involvement = "Monthly";
                state.notifyListeners();
              },
            ),
            const SizedBox(height: 16),

            PillButton(
              text: "Tweak & optimize",
              selected: state.involvement == "Tweak",
              onTap: () {
                state.involvement = "Tweak";
                state.notifyListeners();
              },
            ),

            const Spacer(),

           SafeArea(
              minimum: const EdgeInsets.only(bottom: 16),
              child: SizedBox(
                width: double.infinity,
                height: 54,
                child: FilledButton(
                  onPressed: state.loading
                      ? null
                      : () async {
                          await context.read<AppState>().loadStarter();

                          if (context.mounted) {
                            Navigator.pushAndRemoveUntil(
                              context,
                              MaterialPageRoute(
                                builder: (_) => const StarterPortfolioScreen(),
                              ),
                              (route) => false,
                            );
                          }
                        },
                  child: Text(
                    state.loading ? "Building..." : "Finish",
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                  ),
                ),
              ),
            )
          ],
        ),
      ),
    );
  }
}
