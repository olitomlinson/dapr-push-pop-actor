using System.Runtime.Serialization;

namespace PushPopActor.Interfaces;

/// <summary>
/// Request model for Push operation.
/// </summary>
[DataContract]
public class PushRequest
{
    /// <summary>
    /// The item to push (as JSON string).
    /// </summary>
    [DataMember]
    public string ItemJson { get; set; } = string.Empty;

    /// <summary>
    /// Priority level (0 = highest priority).
    /// </summary>
    [DataMember]
    public int Priority { get; set; } = 0;
}

/// <summary>
/// Response model for Push operation.
/// </summary>
[DataContract]
public class PushResponse
{
    /// <summary>
    /// Whether the push was successful.
    /// </summary>
    [DataMember]
    public bool Success { get; set; }
}

/// <summary>
/// Request model for PopWithAck operation.
/// </summary>
[DataContract]
public class PopWithAckRequest
{
    /// <summary>
    /// Lock TTL in seconds (1-300).
    /// </summary>
    [DataMember]
    public int TtlSeconds { get; set; } = 30;
}

/// <summary>
/// Response model for Pop operation.
/// </summary>
[DataContract]
public class PopResponse
{
    /// <summary>
    /// List of popped items (as JSON strings).
    /// </summary>
    [DataMember]
    public List<string> ItemsJson { get; set; } = new();
}

/// <summary>
/// Response model for PopWithAck operation.
/// </summary>
[DataContract]
public class PopWithAckResponse
{
    /// <summary>
    /// List of popped items (as JSON strings).
    /// </summary>
    [DataMember]
    public List<string> ItemsJson { get; set; } = new();

    /// <summary>
    /// Number of items returned.
    /// </summary>
    [DataMember]
    public int Count { get; set; }

    /// <summary>
    /// Whether the queue is locked.
    /// </summary>
    [DataMember]
    public bool Locked { get; set; }

    /// <summary>
    /// Lock ID for acknowledgement (if locked).
    /// </summary>
    [DataMember]
    public string? LockId { get; set; }

    /// <summary>
    /// Unix timestamp when lock expires.
    /// </summary>
    [DataMember]
    public double? LockExpiresAt { get; set; }

    /// <summary>
    /// Status message.
    /// </summary>
    [DataMember]
    public string? Message { get; set; }
}

/// <summary>
/// Request model for Acknowledge operation.
/// </summary>
[DataContract]
public class AcknowledgeRequest
{
    /// <summary>
    /// Lock ID to acknowledge.
    /// </summary>
    [DataMember]
    public string LockId { get; set; } = string.Empty;
}

/// <summary>
/// Response model for Acknowledge operation.
/// </summary>
[DataContract]
public class AcknowledgeResponse
{
    /// <summary>
    /// Whether the acknowledgement was successful.
    /// </summary>
    [DataMember]
    public bool Success { get; set; }

    /// <summary>
    /// Status message.
    /// </summary>
    [DataMember]
    public string Message { get; set; } = string.Empty;

    /// <summary>
    /// Number of items acknowledged.
    /// </summary>
    [DataMember]
    public int ItemsAcknowledged { get; set; }

    /// <summary>
    /// Error code (if not successful).
    /// </summary>
    [DataMember]
    public string? ErrorCode { get; set; }
}
