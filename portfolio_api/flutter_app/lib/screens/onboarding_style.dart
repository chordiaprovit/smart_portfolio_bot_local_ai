import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';
import '../widgets/pill_button.dart';
import '../screens/onboarding_age_range.dart';

class OnboardingStyleScreen extends StatelessWidget {
  const OnboardingStyleScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();

    return Scaffold(
      appBar: AppBar(
        leading: const SizedBox(),
        title: const Text("Investment Style"),
      ),
      body: Padding(
        padding: const EdgeInsets.only(left: 20, top: 20, right: 20, bottom: 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 12),

            Text(
              "Let’s tailor recommendations for you",
              style: Theme.of(context)
                  .textTheme
                  .bodyLarge
                  ?.copyWith(color: Theme.of(context).colorScheme.onSurfaceVariant),
            ),

            const SizedBox(height: 28),

            PillButton(
              text: "Long-term growth",
              selected: state.investmentStyle == "Long-term",
              onTap: () {
                state.investmentStyle = "Long-term";
                state.notifyListeners();
              },
            ),

            const SizedBox(height: 16),

            PillButton(
              text: "Set it & forget it",
              selected: state.investmentStyle == "Conservative",
              onTap: () {
                state.investmentStyle = "Conservative";
                state.notifyListeners();
              },
            ),

            const SizedBox(height: 16),

            PillButton(
              text: "Active / short-term",
              selected: state.investmentStyle == "Active",
              onTap: () {
                state.investmentStyle = "Active";
                state.notifyListeners();
              },
            ),

            const Spacer(),

            SizedBox(
              width: double.infinity,
              height: 54,
              child: FilledButton(
                onPressed: () {
                  Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (_) => const OnboardingAgeRangeScreen(),
                    ),
                  );
                },
                child: const Text(
                  "Next",
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
