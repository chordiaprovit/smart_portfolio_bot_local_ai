import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/models.dart';
import 'portfolio_service.dart';

class HttpPortfolioService implements PortfolioService {
  final String baseUrl;
  HttpPortfolioService(this.baseUrl);

  Uri _u(String path, [Map<String, String>? q]) =>
      Uri.parse('$baseUrl$path').replace(queryParameters: q);

  @override
  Future<HealthResponse> getHealth({
    required List<HoldingIn> holdings,
    required String focus,
    String? ageRange,
  }) async {
    final res = await http.post(
      _u('/portfolio/health'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        "holdings": holdings.map((h) => h.toJson()).toList(),
        "focus": focus,
        if (ageRange != null) "ageRange": ageRange,
      }),
    );
    if (res.statusCode != 200) throw Exception('Health failed: ${res.statusCode} ${res.body}');
    return HealthResponse.fromJson(jsonDecode(res.body));
  }

  @override
  Future<InsightsResponse> getInsights({
    required List<HoldingIn> holdings,
    required String focus,
    String? ageRange,
  }) async {
    final res = await http.post(
      _u('/portfolio/insights'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        "holdings": holdings.map((h) => h.toJson()).toList(),
        "focus": focus,
        if (ageRange != null) "ageRange": ageRange,
      }),
    );
    if (res.statusCode != 200) throw Exception('Insights failed: ${res.statusCode} ${res.body}');
    return InsightsResponse.fromJson(jsonDecode(res.body));
  }

  @override
  Future<StarterPortfolioResponse> getStarterPortfolio({
    required String investmentStyle,
    required String assetInterest,
    required String focus,
    required String involvement,
    String? ageRange,
  }) async {
    final res = await http.post(
      _u('/starter-portfolio'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        "investmentStyle": investmentStyle,
        "assetInterest": assetInterest,
        "focus": focus,
        "involvement": involvement,
        if (ageRange != null) "ageRange": ageRange,
      }),
    );
    if (res.statusCode != 200) throw Exception('Starter portfolio failed: ${res.statusCode} ${res.body}');
    return StarterPortfolioResponse.fromJson(jsonDecode(res.body));
  }

  @override
  Future<List<String>> searchTickers(String query) async {
    final res = await http.get(_u('/universe/search', {"q": query, "limit": "10"}));
    if (res.statusCode != 200) throw Exception('Search failed: ${res.statusCode} ${res.body}');
    final j = jsonDecode(res.body) as Map<String, dynamic>;
    return List<String>.from(j["results"] as List);
  }

  @override
  String getTickerName(String ticker) {
    // For HTTP service, we could make an API call here, but for now return ticker
    return ticker;
  }
}
