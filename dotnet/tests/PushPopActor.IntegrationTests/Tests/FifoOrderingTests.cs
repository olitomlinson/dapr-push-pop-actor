using System.Net.Http.Json;
using System.Text.Json;
using PushPopActor.IntegrationTests.Fixtures;
using PushPopActor.Interfaces;

namespace PushPopActor.IntegrationTests.Tests;

[Collection("Dapr Collection")]
public class FifoOrderingTests
{
    private readonly DaprTestFixture _fixture;
    private readonly string _queueId = $"test-queue-{Guid.NewGuid():N}";

    public FifoOrderingTests(DaprTestFixture fixture)
    {
        _fixture = fixture;
    }

    [Fact]
    public async Task Push10Items_PopAll_ReturnsInCorrectFifoOrder()
    {
        // Arrange - Push 10 items with sequential IDs
        var expectedIds = new List<int>();
        for (int i = 0; i < 10; i++)
        {
            var itemJson = JsonSerializer.Serialize(new { id = i, value = $"item-{i}" });
            var pushRequest = new { item = JsonDocument.Parse(itemJson).RootElement, priority = 1 };

            var response = await _fixture.ApiClient.PostAsJsonAsync($"/queue/{_queueId}/push", pushRequest);
            var content = await response.Content.ReadAsStringAsync();
            Assert.True(response.IsSuccessStatusCode, $"Push #{i} failed: {response.StatusCode} - {content}");

            expectedIds.Add(i);
        }

        // Give actors a moment to initialize and process
        await Task.Delay(TimeSpan.FromSeconds(5));

        // Act - Pop all 10 items
        var actualIds = new List<int>();
        for (int i = 0; i < 10; i++)
        {
            var response = await _fixture.ApiClient.PostAsync($"/queue/{_queueId}/pop?require_ack=false", null);
            response.EnsureSuccessStatusCode();

            var result = await response.Content.ReadFromJsonAsync<PopResponse>();
            Assert.NotNull(result);
            Assert.NotNull(result.ItemJson);

            var item = JsonSerializer.Deserialize<JsonElement>(result.ItemJson);
            actualIds.Add(item.GetProperty("id").GetInt32());
        }

        // Assert - Verify FIFO ordering
        Assert.Equal(expectedIds, actualIds);

        Task.Delay(TimeSpan.FromMinutes(2));
    }

    [Fact]
    public async Task Push100Items_PopAll_ReturnsInCorrectFifoOrder()
    {
        // Arrange - Push 100 items with sequential IDs
        var expectedIds = new List<int>();
        for (int i = 0; i < 100; i++)
        {
            var itemJson = JsonSerializer.Serialize(new { id = i, value = $"item-{i}" });
            var pushRequest = new { item = JsonDocument.Parse(itemJson).RootElement, priority = 1 };

            var response = await _fixture.ApiClient.PostAsJsonAsync($"/queue/{_queueId}/push", pushRequest);
            response.EnsureSuccessStatusCode();

            expectedIds.Add(i);
        }

        // Act - Pop all 100 items
        var actualIds = new List<int>();
        for (int i = 0; i < 100; i++)
        {
            var response = await _fixture.ApiClient.PostAsync($"/queue/{_queueId}/pop?require_ack=false", null);
            response.EnsureSuccessStatusCode();

            var result = await response.Content.ReadFromJsonAsync<PopResponse>();
            Assert.NotNull(result);
            Assert.NotNull(result.ItemJson);

            var item = JsonSerializer.Deserialize<JsonElement>(result.ItemJson);
            actualIds.Add(item.GetProperty("id").GetInt32());
        }

        // Assert - Verify FIFO ordering
        Assert.Equal(expectedIds, actualIds);

        // Also verify via Dapr Actor HTTP API that queue is empty
        // Note: ActorMetadata check would require deserializing the internal state structure
    }

    [Fact]
    public async Task PushItems_PopEmpty_ReturnsEmptyResult()
    {
        // Arrange - Don't push anything

        // Act - Try to pop from empty queue
        var response = await _fixture.ApiClient.PostAsync($"/queue/{_queueId}/pop?require_ack=false", null);

        // Assert - Should succeed with null result
        response.EnsureSuccessStatusCode();
        var result = await response.Content.ReadFromJsonAsync<PopResponse>();
        Assert.NotNull(result);
        Assert.Null(result.ItemJson);
    }

    [Fact]
    public async Task PushOneItem_PopTwice_SecondPopReturnsEmpty()
    {
        // Arrange - Push 1 item
        var itemJson = JsonSerializer.Serialize(new { id = 1, value = "single-item" });
        var pushRequest = new { item = JsonDocument.Parse(itemJson).RootElement, priority = 1 };
        var pushResponse = await _fixture.ApiClient.PostAsJsonAsync($"/queue/{_queueId}/push", pushRequest);
        pushResponse.EnsureSuccessStatusCode();

        // Act - Pop twice
        var firstPop = await _fixture.ApiClient.PostAsync($"/queue/{_queueId}/pop?require_ack=false", null);
        firstPop.EnsureSuccessStatusCode();
        var firstResult = await firstPop.Content.ReadFromJsonAsync<PopResponse>();

        var secondPop = await _fixture.ApiClient.PostAsync($"/queue/{_queueId}/pop?require_ack=false", null);
        secondPop.EnsureSuccessStatusCode();
        var secondResult = await secondPop.Content.ReadFromJsonAsync<PopResponse>();

        // Assert
        Assert.NotNull(firstResult);
        Assert.NotNull(firstResult.ItemJson);

        Assert.NotNull(secondResult);
        Assert.Null(secondResult.ItemJson);
    }
}
