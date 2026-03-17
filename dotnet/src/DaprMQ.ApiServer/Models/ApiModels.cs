using System.Text.Json;

namespace DaprMQ.ApiServer.Models;

// Request models
public record ApiPushRequest(
    List<ApiPushItem> Items
);

public record ApiPushItem(
    JsonElement Item,
    int Priority = 1
);

public record ApiAcknowledgeRequest(
    string LockId
);

public record ApiExtendLockRequest(
    string LockId,
    int AdditionalTtlSeconds = 30
);

// Response models
public record ApiPushResponse(
    bool Success,
    string Message,
    int ItemsPushed
);

public record ApiPopResponse(
    List<ApiPopItem> Items
);

public record ApiPopItem(
    object Item,
    int Priority
);

public record ApiPopWithAckResponse(
    List<ApiPopWithAckItem> Items,
    bool Locked,
    string? Message = null
);

public record ApiPopWithAckItem(
    object Item,
    int Priority,
    string LockId,
    double LockExpiresAt
);

public record ApiAcknowledgeResponse(
    bool Success,
    string Message,
    int ItemsAcknowledged = 0,
    string? ErrorCode = null
);

public record ApiErrorResponse(
    string Message,
    bool Success = false
);

public record ApiLockedResponse(
    string? Message,
    double? LockExpiresAt
);

public record ApiExtendLockResponse(
    long NewExpiresAt,
    string LockId
);

public record ApiDeadLetterRequest(
    string LockId
);

public record ApiDeadLetterResponse(
    bool Success,
    string Message,
    string? ErrorCode = null,
    string? DlqId = null
);
