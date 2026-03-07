using System.Text.Json;
using Dapr.Actors;
using Microsoft.AspNetCore.Mvc;
using PushPopActor.Interfaces;
using PushPopActor.ApiServer.Abstractions;
using PushPopActor.ApiServer.Constants;
using PushPopActor.ApiServer.Models;
using PushPopActor.ApiServer.Configuration;

namespace PushPopActor.ApiServer.Controllers;

[ApiController]
[Route("queue")]
public class QueueController : ControllerBase
{
    private readonly ILogger<QueueController> _logger;
    private readonly ActorConfiguration _actorConfig;
    private readonly IActorInvoker _actorInvoker;

    public QueueController(
        ILogger<QueueController> logger,
        ActorConfiguration actorConfig,
        IActorInvoker actorInvoker)
    {
        _logger = logger;
        _actorConfig = actorConfig;
        _actorInvoker = actorInvoker;
    }

    /// <summary>
    /// Push an item to the queue with optional priority.
    /// </summary>
    [HttpPost("{queueId}/push")]
    public async Task<IActionResult> Push(
        string queueId,
        [FromBody] ApiPushRequest request)
    {
        try
        {
            if (request.Priority < 0)
            {
                return BadRequest(new ApiErrorResponse("Priority must be non-negative"));
            }

            _logger.LogDebug($"Push request for queue {queueId} with priority {request.Priority}");

            var actorId = new ActorId(queueId);

            // Get raw JSON string from JsonElement (no unnecessary deserialization)
            var itemJson = request.Item.GetRawText();

            var result = await _actorInvoker.InvokeMethodAsync<PushRequest, PushResponse>(
                actorId,
                _actorConfig.ActorTypeName,
                ActorMethodNames.Push,
                new PushRequest
                {
                    ItemJson = itemJson,
                    Priority = request.Priority
                });

            if (result.Success)
            {
                return Ok(new ApiPushResponse(
                    true,
                    $"Item pushed to queue {queueId} at priority {request.Priority}"
                ));
            }

            return BadRequest(new ApiErrorResponse("Failed to push item"));
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, $"Error pushing item to queue {queueId}");
            return StatusCode(500, new ApiErrorResponse($"Internal error: {ex.Message}"));
        }
    }

    /// <summary>
    /// Pop items from the queue with optional acknowledgement.
    /// </summary>
    [HttpPost("{queueId}/pop")]
    public async Task<IActionResult> Pop(
        string queueId,
        [FromHeader] bool require_ack = false,
        [FromHeader] int ttl_seconds = 30)
    {
        try
        {
            _logger.LogDebug($"Pop request for queue {queueId}, require_ack={require_ack}");

            var actorId = new ActorId(queueId);

            if (require_ack)
            {
                var result = await _actorInvoker.InvokeMethodAsync<PopWithAckRequest, PopWithAckResponse>(
                    actorId,
                    _actorConfig.ActorTypeName,
                    ActorMethodNames.PopWithAck,
                    new PopWithAckRequest
                    {
                        TtlSeconds = ttl_seconds
                    });

                // If locked by another operation (Locked=true but no LockId), return 423 Locked
                if (result.Locked && result.LockId == null)
                {
                    return StatusCode(423, new ApiLockedResponse(
                        result.Message,
                        result.LockExpiresAt
                    ));
                }

                // If queue is empty, return 204 No Content
                if (result.IsEmpty)
                {
                    return NoContent();
                }


                return Ok(new ApiPopWithAckResponse(
                JsonDocument.Parse(result.ItemJson).RootElement,
                result.Locked,
                result.LockId,
                result.LockExpiresAt,
                result.Message));

            }
            else
            {
                var result = await _actorInvoker.InvokeMethodAsync<PopResponse>(
                    actorId,
                    _actorConfig.ActorTypeName,
                    ActorMethodNames.Pop);

                // DEBUG: Log what we actually received
                _logger.LogWarning($"[DEBUG] Pop result - ItemJson: '{result.ItemJson ?? "NULL"}', Locked: {result.Locked}, IsEmpty: {result.IsEmpty}, Message: '{result.Message ?? "NULL"}'");

                // If locked by another operation, return 423 Locked
                if (result.Locked)
                {
                    _logger.LogWarning("[DEBUG] Returning 423 Locked");
                    return StatusCode(423, new ApiLockedResponse(
                        result.Message,
                        result.LockExpiresAt
                    ));
                }

                // If queue is empty, return 204 No Content
                // Check both IsEmpty flag and null ItemJson for backwards compatibility
                if (result.IsEmpty)
                {
                    return NoContent();
                }

                return Ok(new ApiPopResponse(JsonDocument.Parse(result.ItemJson).RootElement));
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, $"Error popping item from queue {queueId}");
            return StatusCode(500, new ApiErrorResponse($"Internal error: {ex.Message}"));
        }
    }

    /// <summary>
    /// Acknowledge popped items using lock ID.
    /// </summary>
    [HttpPost("{queueId}/acknowledge")]
    public async Task<IActionResult> Acknowledge(
        string queueId,
        [FromBody] ApiAcknowledgeRequest request)
    {
        try
        {
            _logger.LogDebug($"Acknowledge request for queue {queueId} with lock_id {request.LockId}");

            var actorId = new ActorId(queueId);

            var result = await _actorInvoker.InvokeMethodAsync<AcknowledgeRequest, AcknowledgeResponse>(
                actorId,
                _actorConfig.ActorTypeName,
                ActorMethodNames.Acknowledge,
                new AcknowledgeRequest
                {
                    LockId = request.LockId
                });

            // Check for error codes
            if (!result.Success)
            {
                var response = new ApiAcknowledgeResponse(
                    result.Success,
                    result.Message,
                    ErrorCode: result.ErrorCode
                );

                // Return 410 Gone if lock expired
                if (result.ErrorCode == "LOCK_EXPIRED")
                {
                    return StatusCode(410, response);
                }

                // Return 404 if lock not found
                if (result.ErrorCode == "LOCK_NOT_FOUND")
                {
                    return NotFound(response);
                }

                // Return 400 for invalid lock_id
                if (result.ErrorCode == "INVALID_LOCK_ID")
                {
                    return BadRequest(response);
                }

                // Default to 400 for other failures
                return BadRequest(response);
            }

            return Ok(new ApiAcknowledgeResponse(
                result.Success,
                result.Message,
                result.ItemsAcknowledged
            ));
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, $"Error acknowledging items for queue {queueId}");
            return StatusCode(500, new ApiErrorResponse($"Internal error: {ex.Message}"));
        }
    }
}
