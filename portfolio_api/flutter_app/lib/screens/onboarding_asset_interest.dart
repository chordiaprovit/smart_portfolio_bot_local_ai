import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';
import '../widgets/pill_button.dart';
import 'onboarding_focus.dart';

class OnboardingAssetInterestScreen extends StatelessWidget {
  const OnboardingAssetInterestScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();

    return Scaffold(
      appBar: AppBar(
        title: const Text("Asset Interest"),
      ),
      body: Padding(
        padding: const EdgeInsets.only(left: 20, top: 20, right: 20, bottom: 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 12),

            Text(
              "What do you want to invest in?",
              style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
            ),

            const SizedBox(height: 28),

            PillButton(
              text: "Stocks",
              selected: state.assetInterest == "Stocks",
              onTap: () {
                state.assetInterest = "Stocks";
                state.notifyListeners();
              },
            ),
            const SizedBox(height: 16),

            PillButton(
              text: "ETFs",
              selected: state.assetInterest == "ETFs",
              onTap: () {
                state.assetInterest = "ETFs";
                state.notifyListeners();
              },
            ),
            const SizedBox(height: 16),

            PillButton(
              text: "Bonds",
              selected: state.assetInterest == "Bonds",
              onTap: () {
                state.assetInterest = "Bonds";
                state.notifyListeners();
              },
            ),
            const SizedBox(height: 16),

            PillButton(
              text: "I don’t know",
              selected: state.assetInterest == "I don’t know",
              onTap: () {
                state.assetInterest = "I don’t know";
                state.notifyListeners();
              },
            ),
            const SizedBox(height: 16),


            PillButton(
              text: "All of the above",
              selected: state.assetInterest == "All of the above",
              onTap: () {
                state.assetInterest = "All of the above";
                state.notifyListeners();
              },
            ),
            const SizedBox(height: 16),

            const Spacer(),

            SizedBox(
              width: double.infinity,
              height: 54,
              child: FilledButton(
                onPressed: () {
                  Navigator.push(
                    context,
                    MaterialPageRoute(builder: (_) => const OnboardingFocusScreen()),
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
