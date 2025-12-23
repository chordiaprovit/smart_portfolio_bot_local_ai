import '../models/models.dart';
import 'portfolio_service.dart';

class MockPortfolioService implements PortfolioService {
  @override
  Future<HealthResponse> getHealth({required List<HoldingIn> holdings, required String focus, String? ageRange}) async {
    await Future.delayed(const Duration(milliseconds: 300));
    return HealthResponse(
      asOf: "mock",
      score: 78,
      subScores: SubScores(allocationEquality: 18, concentration: 17, sectorBalance: 20, goalAlignment: 23),
      topRisks: ["Tech exposure is moderately high", "Top holding is above 25%"],
      explainability: {
        "allocationEquality": "Mock explainability for Gini.",
        "concentration": "Mock explainability for top holding.",
        "sectorBalance": "Mock explainability for sector.",
        "goalAlignment": "Mock explainability for goal alignment.",
      },
    );
  }

  @override
  Future<InsightsResponse> getInsights({required List<HoldingIn> holdings, required String focus, String? ageRange}) async {
    await Future.delayed(const Duration(milliseconds: 250));
    return InsightsResponse(asOf: "mock", correlationWarnings: [
      "VOO and SPY move very similarly (corr ≈ 0.99).",
      "QQQ and AAPL are highly correlated (corr ≈ 0.82).",
    ]);
  }

  @override
  Future<StarterPortfolioResponse> getStarterPortfolio({
    required String investmentStyle,
    required String assetInterest,
    required String focus,
    required String involvement,
    String? ageRange,
  }) async {
    await Future.delayed(const Duration(milliseconds: 200));
    return StarterPortfolioResponse(
      asOf: "mock",
      name: "$investmentStyle • $focus",
      allocations: [
        StarterAllocation(ticker: "VOO", type: "etf", name: "Vanguard S&P 500 ETF", weight: 0.60, reason: "Broad US market"),
        StarterAllocation(ticker: "QQQ", type: "etf", name: "Invesco QQQ Trust Series I", weight: 0.25, reason: "Growth tilt"),
        StarterAllocation(ticker: "BND", type: "bond_etf", name: "Vanguard Total Bond Market ETF", weight: 0.15, reason: "Stability buffer"),
      ],
      notes: ["Mock starter portfolio", "Adjust anytime."],
    );
  }

  @override
  Future<List<String>> searchTickers(String query) async {
    await Future.delayed(const Duration(milliseconds: 120));
    return ["VOO", "SPY", "IVV", "VTI", "QQQ"].where((t) => t.contains(query.toUpperCase())).toList();
  }

  @override
  String getTickerName(String ticker) {
    const names = {
      'VOO': 'Vanguard S&P 500 ETF',
      'SPY': 'SPDR S&P 500 ETF Trust',
      'IVV': 'iShares Core S&P 500 ETF',
      'VTI': 'Vanguard Total Stock Market ETF',
      'QQQ': 'Invesco QQQ Trust Series I',
    };
    return names[ticker] ?? ticker;
  }
}
