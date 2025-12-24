import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';
import '../widgets/pill_button.dart';
import 'onboarding_involvement.dart';

class OnboardingFocusScreen extends StatelessWidget {
  const OnboardingFocusScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();

    return Scaffold(
      appBar: AppBar(
        title: const Text("What’s Your Focus?"),
      ),
      body: Padding(
        padding: const EdgeInsets.only(left: 20, top: 20, right: 20, bottom: 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 12),

            Text(
              "Pick the outcome that matters most to you.",
              style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
            ),

            const SizedBox(height: 28),

            PillButton(
              text: "Growth",
              selected: state.focus == "Growth",
              onTap: () {
                state.focus = "Growth";
                state.notifyListeners();
              },
            ),
            const SizedBox(height: 16),

            PillButton(
              text: "Dividend",
              selected: state.focus == "Dividend",
              onTap: () {
                state.focus = "Dividend";
                state.notifyListeners();
              },
            ),
            const SizedBox(height: 16),

            PillButton(
              text: "Stability",
              selected: state.focus == "Stability",
              onTap: () {
                state.focus = "Stability";
                state.notifyListeners();
              },
            ),
            const SizedBox(height: 16),

            PillButton(
              text: "Active returns",
              selected: state.focus == "Active returns",
              onTap: () {
                state.focus = "Active returns";
                state.notifyListeners();
              },
            ),

            const Spacer(),

            SafeArea(
                  minimum: const EdgeInsets.only(bottom: 16),
                  child:
                SizedBox(
                  width: double.infinity,
                  height: 54,
                  child: FilledButton(
                    onPressed: () {
                      Navigator.push(
                        context,
                        MaterialPageRoute(builder: (_) => const OnboardingInvolvementScreen()),
                      );
                    },
                    child: const Text(
                      "Next",
                      style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                    ),
                  ),
                )
            ),
          ],
        ),
      ),
    );
  }
}
