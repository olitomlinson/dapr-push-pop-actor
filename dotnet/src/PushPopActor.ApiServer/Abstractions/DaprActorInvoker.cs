using Dapr.Actors;
using Dapr.Actors.Client;

namespace PushPopActor.ApiServer.Abstractions;

/// <summary>
/// Implementation of IActorInvoker that uses Dapr's ActorProxy.
/// This wrapper enables unit testing by providing a mockable interface.
/// </summary>
public class DaprActorInvoker : IActorInvoker
{
    private readonly IActorProxyFactory _actorProxyFactory;

    public DaprActorInvoker(IActorProxyFactory actorProxyFactory)
    {
        _actorProxyFactory = actorProxyFactory;
    }

    /// <inheritdoc />
    public async Task<TResponse> InvokeMethodAsync<TResponse>(
        ActorId actorId,
        string actorType,
        string methodName,
        CancellationToken cancellationToken = default)
    {
        var proxy = _actorProxyFactory.Create(actorId, actorType);
        return await proxy.InvokeMethodAsync<TResponse>(methodName, cancellationToken);
    }

    /// <inheritdoc />
    public async Task<TResponse> InvokeMethodAsync<TRequest, TResponse>(
        ActorId actorId,
        string actorType,
        string methodName,
        TRequest request,
        CancellationToken cancellationToken = default)
    {
        var proxy = _actorProxyFactory.Create(actorId, actorType);
        return await proxy.InvokeMethodAsync<TRequest, TResponse>(methodName, request, cancellationToken);
    }
}
