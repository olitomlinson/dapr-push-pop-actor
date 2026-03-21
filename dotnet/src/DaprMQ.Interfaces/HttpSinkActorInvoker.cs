using Dapr.Actors.Client;

namespace DaprMQ.Interfaces;

/// <summary>
/// Actor invoker specifically for HttpSinkActor operations.
/// Extends DaprActorInvoker and implements IHttpSinkActorInvoker for type-safe DI.
/// </summary>
public class HttpSinkActorInvoker : DaprActorInvoker, IHttpSinkActorInvoker
{
    public HttpSinkActorInvoker(IActorProxyFactory actorProxyFactory)
        : base(actorProxyFactory, "HttpSinkActor")
    {
    }
}
