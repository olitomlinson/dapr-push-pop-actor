using PushPopActor.IntegrationTests.Infrastructure;

namespace PushPopActor.IntegrationTests.Fixtures;

/// <summary>
/// xUnit collection fixture for sharing Dapr test environment across test classes
/// This ensures containers are started once and reused across all integration tests
/// </summary>
public class DaprTestFixture : IAsyncLifetime
{
    public DaprTestEnvironment Environment { get; private set; } = null!;
    public HttpClient ApiClient => Environment.ApiClient;
    public HttpClient DaprSidecarClient => Environment.DaprSidecarClient;
    public DaprActorHttpClient ActorClient { get; private set; } = null!;

    public async Task InitializeAsync()
    {
        Environment = new DaprTestEnvironment();
        await Environment.InitializeAsync();

        ActorClient = new DaprActorHttpClient(Environment.DaprSidecarClient);
    }

    public async Task DisposeAsync()
    {
        if (Environment != null)
        {
            await Environment.DisposeAsync();
        }
    }
}

/// <summary>
/// Collection definition for xUnit
/// All test classes decorated with [Collection("Dapr Collection")] will share this fixture
/// </summary>
[CollectionDefinition("Dapr Collection")]
public class DaprCollection : ICollectionFixture<DaprTestFixture>
{
    // This class has no code, and is never created. Its purpose is simply
    // to be the place to apply [CollectionDefinition] and all the
    // ICollectionFixture<> interfaces.
}
