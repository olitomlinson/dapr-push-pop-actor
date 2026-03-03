using PushPopActor.IntegrationTests.Fixtures;

namespace PushPopActor.IntegrationTests.Tests;

[Collection("Dapr Collection")]
public class NetworkDebugTest
{
    private readonly DaprTestFixture _fixture;

    public NetworkDebugTest(DaprTestFixture fixture)
    {
        _fixture = fixture;
    }

    [Fact]
    public async Task InspectNetwork()
    {
        Console.WriteLine($"API URL: {_fixture.Environment.ApiServerUrl}");
        Console.WriteLine($"Dapr HTTP: {_fixture.Environment.DaprHttpEndpoint}");
        
        // Keep test alive for 2 minutes to inspect containers
        Console.WriteLine("Sleeping for 120 seconds to allow inspection...");
        await Task.Delay(TimeSpan.FromMinutes(2));
        
        Assert.True(true);
    }
}
