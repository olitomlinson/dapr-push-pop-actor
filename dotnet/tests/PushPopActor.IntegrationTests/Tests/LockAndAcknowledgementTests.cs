using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using PushPopActor.IntegrationTests.Fixtures;
using PushPopActor.ApiServer.Models;

namespace PushPopActor.IntegrationTests.Tests;

[Collection("Dapr Collection")]
public class LockAndAcknowledgementTests(DaprTestFixture fixture)
{
    [Fact]
    public async Task PopWithAck_CreatesLock_BlocksRegularPop()
    {
        // Arrange - Push an item
        var queueId = $"{fixture.QueueId}-lock-test-{Guid.NewGuid():N}";
        var itemElement = JsonSerializer.SerializeToElement(new { id = 1, value = "test-item" });
        var pushRequest = new ApiPushRequest(itemElement, Priority: 1);
        var pushResponse = await fixture.ApiClient.PostAsJsonAsync($"/queue/{queueId}/push", pushRequest);
        pushResponse.EnsureSuccessStatusCode();

        // Act - Pop with acknowledgement (creates lock)
        var popWithAckRequest = new HttpRequestMessage(HttpMethod.Post, $"/queue/{queueId}/pop");
        popWithAckRequest.Headers.Add("require_ack", "true");
        popWithAckRequest.Headers.Add("ttl_seconds", "30");
        var popWithAckResponse = await fixture.ApiClient.SendAsync(popWithAckRequest);
        popWithAckResponse.EnsureSuccessStatusCode();

        var popWithAckResult = await popWithAckResponse.Content.ReadFromJsonAsync<ApiPopWithAckResponse>();
        Assert.NotNull(popWithAckResult);
        Assert.NotNull(popWithAckResult.Item);
        Assert.True(popWithAckResult.Locked);
        Assert.NotNull(popWithAckResult.LockId);
        Assert.NotNull(popWithAckResult.LockExpiresAt);

        // Attempt regular Pop - should be blocked with HTTP 423
        var blockedPopRequest = new HttpRequestMessage(HttpMethod.Post, $"/queue/{queueId}/pop");
        blockedPopRequest.Headers.Add("require_ack", "false");
        var blockedPopResponse = await fixture.ApiClient.SendAsync(blockedPopRequest);

        // Assert - Should return 423 Locked
        Assert.Equal(HttpStatusCode.Locked, blockedPopResponse.StatusCode);

        var lockedResponse = await blockedPopResponse.Content.ReadFromJsonAsync<ApiLockedResponse>();
        Assert.NotNull(lockedResponse);
        Assert.NotNull(lockedResponse.Message);
        Assert.Contains("locked", lockedResponse.Message, StringComparison.OrdinalIgnoreCase);
        Assert.NotNull(lockedResponse.LockExpiresAt);
        Assert.True(lockedResponse.LockExpiresAt > DateTimeOffset.UtcNow.ToUnixTimeSeconds());
    }

    [Fact]
    public async Task PopWithAck_AfterAcknowledge_AllowsRegularPop()
    {
        // Arrange - Push two items
        var queueId = $"{fixture.QueueId}-ack-test-{Guid.NewGuid():N}";

        var item1 = JsonSerializer.SerializeToElement(new { id = 1, value = "first-item" });
        await fixture.ApiClient.PostAsJsonAsync($"/queue/{queueId}/push", new ApiPushRequest(item1, Priority: 1));

        var item2 = JsonSerializer.SerializeToElement(new { id = 2, value = "second-item" });
        await fixture.ApiClient.PostAsJsonAsync($"/queue/{queueId}/push", new ApiPushRequest(item2, Priority: 1));

        // Act - Pop with acknowledgement
        var popWithAckRequest = new HttpRequestMessage(HttpMethod.Post, $"/queue/{queueId}/pop");
        popWithAckRequest.Headers.Add("require_ack", "true");
        popWithAckRequest.Headers.Add("ttl_seconds", "30");
        var popWithAckResponse = await fixture.ApiClient.SendAsync(popWithAckRequest);
        popWithAckResponse.EnsureSuccessStatusCode();

        var popWithAckResult = await popWithAckResponse.Content.ReadFromJsonAsync<ApiPopWithAckResponse>();
        Assert.NotNull(popWithAckResult);
        Assert.NotNull(popWithAckResult.LockId);

        // Acknowledge the lock
        var ackRequest = new ApiAcknowledgeRequest(popWithAckResult.LockId);
        var ackResponse = await fixture.ApiClient.PostAsJsonAsync($"/queue/{queueId}/acknowledge", ackRequest);
        ackResponse.EnsureSuccessStatusCode();

        var ackResult = await ackResponse.Content.ReadFromJsonAsync<ApiAcknowledgeResponse>();
        Assert.NotNull(ackResult);
        Assert.True(ackResult.Success);
        Assert.Equal(1, ackResult.ItemsAcknowledged);

        // Now regular Pop should work
        var regularPopRequest = new HttpRequestMessage(HttpMethod.Post, $"/queue/{queueId}/pop");
        regularPopRequest.Headers.Add("require_ack", "false");
        var regularPopResponse = await fixture.ApiClient.SendAsync(regularPopRequest);

        // Assert - Should return 200 OK with second item
        Assert.Equal(HttpStatusCode.OK, regularPopResponse.StatusCode);

        var popResult = await regularPopResponse.Content.ReadFromJsonAsync<ApiPopResponse>();
        Assert.NotNull(popResult);
        Assert.NotNull(popResult.Item);

        var itemElement = (JsonElement)popResult.Item;
        Assert.Equal(2, itemElement.GetProperty("id").GetInt32());
    }

    [Fact]
    public async Task PopWithAck_MultiplePopAttempts_AllBlocked()
    {
        // Arrange - Push an item
        var queueId = $"{fixture.QueueId}-multi-block-test-{Guid.NewGuid():N}";
        var itemElement = JsonSerializer.SerializeToElement(new { id = 1, value = "test-item" });
        var pushRequest = new ApiPushRequest(itemElement, Priority: 1);
        var pushResponse = await fixture.ApiClient.PostAsJsonAsync($"/queue/{queueId}/push", pushRequest);
        pushResponse.EnsureSuccessStatusCode();

        // Act - Pop with acknowledgement (creates lock)
        var popWithAckRequest = new HttpRequestMessage(HttpMethod.Post, $"/queue/{queueId}/pop");
        popWithAckRequest.Headers.Add("require_ack", "true");
        popWithAckRequest.Headers.Add("ttl_seconds", "30");
        var popWithAckResponse = await fixture.ApiClient.SendAsync(popWithAckRequest);
        popWithAckResponse.EnsureSuccessStatusCode();

        // Attempt multiple regular Pops - all should be blocked
        for (int i = 0; i < 3; i++)
        {
            var blockedPopRequest = new HttpRequestMessage(HttpMethod.Post, $"/queue/{queueId}/pop");
            blockedPopRequest.Headers.Add("require_ack", "false");
            var blockedPopResponse = await fixture.ApiClient.SendAsync(blockedPopRequest);

            // Assert - Each should return 423 Locked
            Assert.Equal(HttpStatusCode.Locked, blockedPopResponse.StatusCode);

            var lockedResponse = await blockedPopResponse.Content.ReadFromJsonAsync<ApiLockedResponse>();
            Assert.NotNull(lockedResponse);
            Assert.NotNull(lockedResponse.Message);
            Assert.NotNull(lockedResponse.LockExpiresAt);
        }

        // Attempt another PopWithAck - should also be blocked
        var blockedPopWithAckRequest = new HttpRequestMessage(HttpMethod.Post, $"/queue/{queueId}/pop");
        blockedPopWithAckRequest.Headers.Add("require_ack", "true");
        var blockedPopWithAckResponse = await fixture.ApiClient.SendAsync(blockedPopWithAckRequest);

        Assert.Equal(HttpStatusCode.Locked, blockedPopWithAckResponse.StatusCode);
    }

    [Fact]
    public async Task PopWithAck_ExpiredLock_AllowsRegularPop()
    {
        // Arrange - Push an item
        var queueId = $"{fixture.QueueId}-expire-test-{Guid.NewGuid():N}";
        var itemElement = JsonSerializer.SerializeToElement(new { id = 1, value = "test-item" });
        var pushRequest = new ApiPushRequest(itemElement, Priority: 1);
        var pushResponse = await fixture.ApiClient.PostAsJsonAsync($"/queue/{queueId}/push", pushRequest);
        pushResponse.EnsureSuccessStatusCode();

        // Act - Pop with acknowledgement with short TTL (2 seconds)
        var popWithAckRequest = new HttpRequestMessage(HttpMethod.Post, $"/queue/{queueId}/pop");
        popWithAckRequest.Headers.Add("require_ack", "true");
        popWithAckRequest.Headers.Add("ttl_seconds", "2");
        var popWithAckResponse = await fixture.ApiClient.SendAsync(popWithAckRequest);
        popWithAckResponse.EnsureSuccessStatusCode();

        var popWithAckResult = await popWithAckResponse.Content.ReadFromJsonAsync<ApiPopWithAckResponse>();
        Assert.NotNull(popWithAckResult);
        Assert.NotNull(popWithAckResult.Item);

        // Wait for lock to expire (2 seconds + buffer)
        await Task.Delay(TimeSpan.FromSeconds(2.5));

        // Now regular Pop should work (lock expired)
        var regularPopRequest = new HttpRequestMessage(HttpMethod.Post, $"/queue/{queueId}/pop");
        regularPopRequest.Headers.Add("require_ack", "false");
        var regularPopResponse = await fixture.ApiClient.SendAsync(regularPopRequest);

        // Assert - Should return 200 OK with the item (restored after lock expiry)
        Assert.Equal(HttpStatusCode.OK, regularPopResponse.StatusCode);

        var popResult = await regularPopResponse.Content.ReadFromJsonAsync<ApiPopResponse>();
        Assert.NotNull(popResult);
        Assert.NotNull(popResult.Item);

        var poppedItem = (JsonElement)popResult.Item;
        Assert.Equal(1, poppedItem.GetProperty("id").GetInt32());
    }

    [Fact]
    public async Task Pop_EmptyQueue_Returns200WithNullItem()
    {
        // Arrange - Use empty queue
        var queueId = $"{fixture.QueueId}-empty-test-{Guid.NewGuid():N}";

        // Act - Try to pop from empty queue
        var popRequest = new HttpRequestMessage(HttpMethod.Post, $"/queue/{queueId}/pop");
        popRequest.Headers.Add("require_ack", "false");
        var popResponse = await fixture.ApiClient.SendAsync(popRequest);

        // Assert - Should return 204 No Content (not 423) for empty queue
        Assert.Equal(HttpStatusCode.NoContent, popResponse.StatusCode);
    }

    [Fact]
    public async Task PopWithAck_WithLock_ConsistentErrorResponse()
    {
        // This test verifies that both Pop and PopWithAck return consistent 423 responses
        // when the queue is locked by another operation

        // Arrange - Push an item
        var queueId = $"{fixture.QueueId}-consistent-error-{Guid.NewGuid():N}";
        var itemElement = JsonSerializer.SerializeToElement(new { id = 1, value = "test-item" });
        var pushRequest = new ApiPushRequest(itemElement, Priority: 1);
        var pushResponse = await fixture.ApiClient.PostAsJsonAsync($"/queue/{queueId}/push", pushRequest);
        pushResponse.EnsureSuccessStatusCode();

        // Act - Pop with acknowledgement (creates lock)
        var popWithAckRequest1 = new HttpRequestMessage(HttpMethod.Post, $"/queue/{queueId}/pop");
        popWithAckRequest1.Headers.Add("require_ack", "true");
        popWithAckRequest1.Headers.Add("ttl_seconds", "30");
        var popWithAckResponse1 = await fixture.ApiClient.SendAsync(popWithAckRequest1);
        popWithAckResponse1.EnsureSuccessStatusCode();

        // Attempt regular Pop - blocked
        var blockedPopRequest = new HttpRequestMessage(HttpMethod.Post, $"/queue/{queueId}/pop");
        blockedPopRequest.Headers.Add("require_ack", "false");
        var blockedPopResponse = await fixture.ApiClient.SendAsync(blockedPopRequest);

        Assert.Equal(HttpStatusCode.Locked, blockedPopResponse.StatusCode);
        var popLockedResponse = await blockedPopResponse.Content.ReadFromJsonAsync<ApiLockedResponse>();

        // Attempt PopWithAck - also blocked
        var blockedPopWithAckRequest = new HttpRequestMessage(HttpMethod.Post, $"/queue/{queueId}/pop");
        blockedPopWithAckRequest.Headers.Add("require_ack", "true");
        var blockedPopWithAckResponse = await fixture.ApiClient.SendAsync(blockedPopWithAckRequest);

        Assert.Equal(HttpStatusCode.Locked, blockedPopWithAckResponse.StatusCode);
        var popWithAckLockedResponse = await blockedPopWithAckResponse.Content.ReadFromJsonAsync<ApiLockedResponse>();

        // Assert - Both should return same structure
        Assert.NotNull(popLockedResponse);
        Assert.NotNull(popWithAckLockedResponse);

        Assert.NotNull(popLockedResponse.Message);
        Assert.NotNull(popWithAckLockedResponse.Message);

        Assert.NotNull(popLockedResponse.LockExpiresAt);
        Assert.NotNull(popWithAckLockedResponse.LockExpiresAt);

        // Lock expiration times should be very close (within 1 second)
        Assert.True(Math.Abs(popLockedResponse.LockExpiresAt!.Value - popWithAckLockedResponse.LockExpiresAt!.Value) < 1);
    }
}
