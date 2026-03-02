using Dapr.Actors;

namespace PushPopActor.Interfaces;

/// <summary>
/// Interface for the PushPopActor - a FIFO queue-based Dapr actor with priority support.
/// </summary>
public interface IPushPopActor : IActor
{
    /// <summary>
    /// Push an item to the queue with optional priority.
    /// </summary>
    /// <param name="request">Push request containing item JSON and priority</param>
    /// <returns>Push response with success status</returns>
    Task<PushResponse> Push(PushRequest request);

    /// <summary>
    /// Pop a single item from the queue (FIFO, lowest priority first).
    /// </summary>
    /// <returns>Pop response with items as JSON strings</returns>
    Task<PopResponse> Pop();

    /// <summary>
    /// Pop items with acknowledgement requirement (creates a lock).
    /// </summary>
    /// <param name="request">PopWithAck request containing TTL seconds</param>
    /// <returns>PopWithAck response with items, lock info, and status</returns>
    Task<PopWithAckResponse> PopWithAck(PopWithAckRequest request);

    /// <summary>
    /// Acknowledge popped items using lock ID.
    /// </summary>
    /// <param name="request">Acknowledge request containing lock_id</param>
    /// <returns>Acknowledge response with success status and details</returns>
    Task<AcknowledgeResponse> Acknowledge(AcknowledgeRequest request);
}
