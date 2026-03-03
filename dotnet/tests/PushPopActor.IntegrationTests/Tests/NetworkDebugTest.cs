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

        Assert.True(true);
    }
}
