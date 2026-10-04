/// A failed API call. [code] is the server's stable error code (problem+json `code`), or `network` when the
/// server could not be reached; the text shown to the driver comes from the server catalog ([Catalog]).
class ApiError implements Exception {
  ApiError(this.status, this.code, {this.params = const {}, this.body = const {}});

  final int status;
  final String code;
  final Map<String, dynamic> params;
  final Map<String, dynamic> body;

  bool get isNetwork => status == 0;

  /// Worth retrying later (no network, server trouble); anything else is the server's final answer.
  bool get isTransient => status == 0 || status == 408 || status == 429 || status >= 500;

  @override
  String toString() => 'ApiError($status, $code)';
}

/// This phone is no longer bound (logged out elsewhere, replaced by a new phone, token reuse, employment ended).
class SessionEnded implements Exception {
  @override
  String toString() => 'SessionEnded';
}
