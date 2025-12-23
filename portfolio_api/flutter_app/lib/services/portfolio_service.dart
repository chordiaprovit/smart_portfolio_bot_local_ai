import '../models/models.dart';

abstract class PortfolioService {
  Future<HealthResponse> getHealth({
    required List<HoldingIn> holdings,
    required String focus,
    String? ageRange,
  });

  Future<InsightsResponse> getInsights({
    required List<HoldingIn> holdings,
    required String focus,
    String? ageRange,
  });

  Future<StarterPortfolioResponse> getStarterPortfolio({
    required String investmentStyle,
    required String assetInterest,
    required String focus,
    required String involvement,
    String? ageRange,
  });

  Future<List<String>> searchTickers(String query);

  String getTickerName(String ticker);
}
