using System.Net.Http.Json;
using System.Text.Json;
using PushPopActor.IntegrationTests.Fixtures;
using PushPopActor.Interfaces;

namespace PushPopActor.IntegrationTests.Tests;

[Collection("Dapr Collection")]
public class DebugTest
{
    private readonly DaprTestFixture _fixture;

    public DebugTest(DaprTestFixture fixture)
    {
        _fixture = fixture;
    }

    [Fact]
    public async Task TestConnection()
    {
        // Test health endpoint first
        var healthResponse = await _fixture.ApiClient.GetAsync("/health");
        var healthContent = await healthResponse.Content.ReadAsStringAsync();
        Console.WriteLine($"Health: {healthResponse.StatusCode} - {healthContent}");

        // Try to push an item and see what error we get
        var itemJson = JsonSerializer.Serialize(new { id = 1, value = "test" });
        var pushRequest = new { item = JsonDocument.Parse(itemJson).RootElement, priority = 1 };

        var response = await _fixture.ApiClient.PostAsJsonAsync("/queue/test-queue/push", pushRequest);
        var content = await response.Content.ReadAsStringAsync();
        Console.WriteLine($"Push: {response.StatusCode} - {content}");

        Assert.True(response.IsSuccessStatusCode, $"Failed with: {content}");

        Thread.Sleep(TimeSpan.FromSeconds(60));
    }
}
