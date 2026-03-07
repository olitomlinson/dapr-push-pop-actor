using Dapr.Actors;

namespace PushPopActor.ApiServer.Abstractions;

/// <summary>
/// Abstraction for invoking actor methods.
/// This interface wraps Dapr's ActorProxy.InvokeMethodAsync to enable unit testing.
/// </summary>
public interface IActorInvoker
{
    /// <summary>
    /// Invokes an actor method with no request data and returns a response.
    /// </summary>
    Task<TResponse> InvokeMethodAsync<TResponse>(ActorId actorId, string actorType, string methodName, CancellationToken cancellationToken = default);

    /// <summary>
    /// Invokes an actor method with request data and returns a response.
    /// </summary>
    Task<TResponse> InvokeMethodAsync<TRequest, TResponse>(ActorId actorId, string actorType, string methodName, TRequest request, CancellationToken cancellationToken = default);
}
