namespace PushPopActor.ApiServer.Constants;

/// <summary>
/// Actor method names for nonremoting invocations.
/// </summary>
public static class ActorMethodNames
{
    public const string Push = "Push";
    public const string Pop = "Pop";
    public const string PopWithAck = "PopWithAck";
    public const string Acknowledge = "Acknowledge";
}
