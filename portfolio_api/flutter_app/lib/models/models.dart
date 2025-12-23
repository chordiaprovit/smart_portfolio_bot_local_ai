class HoldingIn {
  final String ticker;
  final double weight;
  final String type; // 'etf' or 'stock'
  
  HoldingIn({required this.ticker, required this.weight, required this.type});
  Map<String, dynamic> toJson() => {"ticker": ticker, "weight": weight};
}

class SubScores {
  final int allocationEquality;
  final int concentration;
  final int sectorBalance;
  final int goalAlignment;

  SubScores({
    required this.allocationEquality,
    required this.concentration,
    required this.sectorBalance,
    required this.goalAlignment,
  });

  factory SubScores.fromJson(Map<String, dynamic> j) => SubScores(
        allocationEquality: j["allocationEquality"] as int,
        concentration: j["concentration"] as int,
        sectorBalance: j["sectorBalance"] as int,
        goalAlignment: j["goalAlignment"] as int,
      );
}

class HealthResponse {
  final String? asOf;
  final int score;
  final SubScores subScores;
  final List<String> topRisks;
  final Map<String, String> explainability;

  HealthResponse({
    required this.asOf,
    required this.score,
    required this.subScores,
    required this.topRisks,
    required this.explainability,
  });

  factory HealthResponse.fromJson(Map<String, dynamic> j) => HealthResponse(
        asOf: j["asOf"] as String?,
        score: j["score"] as int,
        subScores: SubScores.fromJson(Map<String, dynamic>.from(j["subScores"] as Map)),
        topRisks: List<String>.from(j["topRisks"] as List),
        explainability: Map<String, String>.from(j["explainability"] as Map),
      );
}

class InsightsResponse {
  final String? asOf;
  final List<String> correlationWarnings;

  InsightsResponse({required this.asOf, required this.correlationWarnings});

  factory InsightsResponse.fromJson(Map<String, dynamic> j) => InsightsResponse(
        asOf: j["asOf"] as String?,
        correlationWarnings: List<String>.from(j["correlationWarnings"] as List),
      );
}

class StarterAllocation {
  final String ticker;
  final String type;
  final String name;
  final double weight;
  final String reason;

  StarterAllocation({
    required this.ticker,
    required this.type,
    required this.name,
    required this.weight,
    required this.reason,
  });

  factory StarterAllocation.fromJson(Map<String, dynamic> j) => StarterAllocation(
        ticker: j["ticker"] as String,
        type: j["type"] as String,
        name: j["name"] as String,
        weight: (j["weight"] as num).toDouble(),
        reason: j["reason"] as String,
      );
}

class StarterPortfolioResponse {
  final String? asOf;
  final String name;
  final List<StarterAllocation> allocations;
  final List<String> notes;

  StarterPortfolioResponse({
    required this.asOf,
    required this.name,
    required this.allocations,
    required this.notes,
  });

  factory StarterPortfolioResponse.fromJson(Map<String, dynamic> j) => StarterPortfolioResponse(
        asOf: j["asOf"] as String?,
        name: j["name"] as String,
        allocations: (j["allocations"] as List)
            .map((e) => StarterAllocation.fromJson(Map<String, dynamic>.from(e as Map)))
            .toList(),
        notes: List<String>.from(j["notes"] as List),
      );
}
