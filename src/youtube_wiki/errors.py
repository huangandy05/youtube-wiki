"""Domain errors shown by the application without leaking provider internals."""


class YouTubeWikiError(Exception):
    """Base class for expected application errors."""


class ConfigurationError(YouTubeWikiError):
    pass


class InvalidChannelUrl(YouTubeWikiError):
    pass


class UnsupportedUrl(InvalidChannelUrl):
    pass


class ChannelNotFound(YouTubeWikiError):
    pass


class ApiRequestError(YouTubeWikiError):
    pass


class ApiKeyInvalid(ApiRequestError):
    pass


class QuotaExceeded(ApiRequestError):
    pass


class RateLimited(YouTubeWikiError):
    pass


class NoTranscriptAvailable(YouTubeWikiError):
    pass


class VideoUnavailable(YouTubeWikiError):
    pass


class LiveTranscriptUnsupported(YouTubeWikiError):
    pass


class ExtractionFailed(YouTubeWikiError):
    pass

