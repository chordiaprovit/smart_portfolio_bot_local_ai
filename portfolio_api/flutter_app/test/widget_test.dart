import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:portfolio_health_app/state/app_state.dart';
import 'package:portfolio_health_app/services/mock_portfolio_service.dart';
import 'package:portfolio_health_app/screens/onboarding_style.dart';

void main() {
  testWidgets('App starts on onboarding style screen', (WidgetTester tester) async {
    await tester.pumpWidget(
      ChangeNotifierProvider(
        create: (_) => AppState(MockPortfolioService()),
        child: MaterialApp(
          theme: ThemeData.dark(useMaterial3: true),
          home: const OnboardingStyleScreen(),
        ),
      ),
    );

    // Verify onboarding screen content
    expect(find.text('Investment Style'), findsOneWidget);
    expect(find.text('Long-term growth'), findsOneWidget);
    expect(find.text('Set it & forget it'), findsOneWidget);
    expect(find.text('Active / short-term'), findsOneWidget);
  });
}
