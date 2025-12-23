import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'screens/splash_screen.dart';
import 'services/local_portfolio_service.dart';
import 'state/app_state.dart';

void main() {
  // No endpoints. Everything runs locally using assets/analytics_pack.json.
  final service = LocalPortfolioService();

  runApp(
    ChangeNotifierProvider(
      create: (_) => AppState(service),
      child: const App(),
    ),
  );
}

class App extends StatelessWidget {
  const App({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Portfolio Health',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark(useMaterial3: true),
      home: const SplashScreen(),
    );
  }
}
