import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';
import '../widgets/pill_button.dart';
import 'onboarding_asset_interest.dart';

class OnboardingAgeRangeScreen extends StatelessWidget {
  const OnboardingAgeRangeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();

    return Scaffold(
      appBar: AppBar(
        title: const Text("Your Investing Stage"),
      ),
      body: Padding(
        padding: const EdgeInsets.only(left: 20, top: 20, right: 20, bottom: 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 12),

            Text(
              "This helps us interpret risk and stability better.",
              style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
            ),

            const SizedBox(height: 28),

            PillButton(
              text: "Early career (20–35)",
              selected: state.ageRange == "20-35",
              onTap: () {
                state.ageRange = "20-35";
                state.notifyListeners();
              },
            ),
            const SizedBox(height: 16),

            PillButton(
              text: "Mid career (36–50)",
              selected: state.ageRange == "36-50",
              onTap: () {
                state.ageRange = "36-50";
                state.notifyListeners();
              },
            ),
            const SizedBox(height: 16),

            PillButton(
              text: "Pre-retirement (51–65)",
              selected: state.ageRange == "51-65",
              onTap: () {
                state.ageRange = "51-65";
                state.notifyListeners();
              },
            ),
            const SizedBox(height: 16),

            PillButton(
              text: "Retired (65+)",
              selected: state.ageRange == "65+",
              onTap: () {
                state.ageRange = "65+";
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
                  onPressed: () {
                    Navigator.push(
                      context,
                      MaterialPageRoute(
                        builder: (_) => const OnboardingAssetInterestScreen(),
                      ),
                    );
                  },
                  child: const Text(
                    "Next",
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
