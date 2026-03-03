namespace PushPopActor.Interfaces;

/// <summary>
/// Request model for Push operation.
/// </summary>
public record PushRequest
{
    /// <summary>
    /// The item to push (as JSON string).
    /// </summary>
    public string ItemJson { get; init; } = string.Empty;

    /// <summary>
    /// Priority level (0 = highest priority, default: 1).
    /// </summary>
    public int Priority { get; init; } = 1;
}

/// <summary>
/// Response model for Push operation.
/// </summary>
public record PushResponse
{
    /// <summary>
    /// Whether the push was successful.
    /// </summary>
    public bool Success { get; init; }
}

/// <summary>
/// Request model for PopWithAck operation.
/// </summary>
public record PopWithAckRequest
{
    /// <summary>
    /// Lock TTL in seconds (1-300).
    /// </summary>
    public int TtlSeconds { get; init; } = 30;
}

/// <summary>
/// Response model for Pop operation.
/// </summary>
public record PopResponse
{
    /// <summary>
    /// The popped item (as JSON string), or null if queue is empty.
    /// </summary>
    public string? ItemJson { get; init; }
}

/// <summary>
/// Response model for PopWithAck operation.
/// </summary>
public record PopWithAckResponse
{
    /// <summary>
    /// The popped item (as JSON string), or null if queue is empty or locked.
    /// </summary>
    public string? ItemJson { get; init; }

    /// <summary>
    /// Whether the queue is locked.
    /// </summary>
    public bool Locked { get; init; }

    /// <summary>
    /// Lock ID for acknowledgement (if locked).
    /// </summary>
    public string? LockId { get; init; }

    /// <summary>
    /// Unix timestamp when lock expires.
    /// </summary>
    public double? LockExpiresAt { get; init; }

    /// <summary>
    /// Status message.
    /// </summary>
    public string? Message { get; init; }
}

/// <summary>
/// Request model for Acknowledge operation.
/// </summary>
public record AcknowledgeRequest
{
    /// <summary>
    /// Lock ID to acknowledge.
    /// </summary>
    public string LockId { get; init; } = string.Empty;
}

/// <summary>
/// Response model for Acknowledge operation.
/// </summary>
public record AcknowledgeResponse
{
    /// <summary>
    /// Whether the acknowledgement was successful.
    /// </summary>
    public bool Success { get; init; }

    /// <summary>
    /// Status message.
    /// </summary>
    public string Message { get; init; } = string.Empty;

    /// <summary>
    /// Number of items acknowledged.
    /// </summary>
    public int ItemsAcknowledged { get; init; }

    /// <summary>
    /// Error code (if not successful).
    /// </summary>
    public string? ErrorCode { get; init; }
}
