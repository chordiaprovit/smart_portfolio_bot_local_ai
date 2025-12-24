import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';
import 'onboarding_style.dart';

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    final state = context.read<AppState>();

    try {
      await state.loadStarter(); 
    } catch (_) {
      // ignore errors — onboarding can still proceed
    }

    await Future.delayed(const Duration(milliseconds: 1500));

    if (!mounted) return;

    Navigator.pushReplacement(
      context,
      MaterialPageRoute(builder: (_) => const OnboardingStyleScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.surface,
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Image.asset(
              'assets/app_icon.png',
              width: 120,
              height: 120,
            ),
            const SizedBox(height: 24),
            const CircularProgressIndicator(),
            const SizedBox(height: 16),
            Text(
              "Analyzing portfolios, not trading them",
              style: TextStyle(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 32),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                _buildKeywordChip("Understand"),
                const SizedBox(width: 8, height: 10),
                _buildKeywordChip("Balance"),
                const SizedBox(width: 8),
                _buildKeywordChip("De-risk"),
                const SizedBox(width: 8),
                _buildKeywordChip("Improve"),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildKeywordChip(String keyword) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.primaryContainer,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Text(
        keyword,
        style: TextStyle(
          color: Theme.of(context).colorScheme.onPrimaryContainer,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }
}
