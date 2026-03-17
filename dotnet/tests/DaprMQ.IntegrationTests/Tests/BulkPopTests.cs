using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Grpc.Core;
using Grpc.Net.Client;
using DaprMQ.IntegrationTests.Fixtures;
using DaprMQ.ApiServer.Models;
using DaprMQ.ApiServer.Grpc;
using GrpcService = DaprMQ.ApiServer.Grpc.DaprMQ;

namespace DaprMQ.IntegrationTests.Tests;

[Collection("Dapr Collection")]
public class BulkPopTests(DaprTestFixture fixture)
{
    // HTTP Bulk Pop Tests

    [Fact]
    public async Task BulkPop_Count10_ReturnsAllItemsInFifoOrder()
    {
        // Arrange - Push 10 items
        var queueId = $"{fixture.QueueId}-bulk10-{Guid.NewGuid():N}";
        var expectedIds = new List<int>();

        for (int i = 0; i < 10; i++)
        {
            var itemElement = JsonSerializer.SerializeToElement(new { id = i, value = $"item-{i}" });
            await fixture.ApiClient.PostAsJsonAsync($"/queue/{queueId}/push",
                new ApiPushRequest(new List<ApiPushItem> { new ApiPushItem(itemElement, Priority: 1) }));
            expectedIds.Add(i);
        }

        // Act - Bulk pop all 10 items
        var popRequest = new HttpRequestMessage(HttpMethod.Post, $"/queue/{queueId}/pop");
        popRequest.Headers.Add("count", "10");
        var response = await fixture.ApiClient.SendAsync(popRequest);

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var result = await response.Content.ReadFromJsonAsync<ApiPopResponse>();
        Assert.NotNull(result);
        Assert.NotNull(result.Items);
        Assert.Equal(10, result.Items.Count);

        var actualIds = result.Items.Select(popItem =>
            ((JsonElement)popItem.Item).GetProperty("id").GetInt32()).ToList();
        Assert.Equal(expectedIds, actualIds);
    }

    [Fact]
    public async Task BulkPop_CrossPriority_ReturnsInPriorityOrder()
    {
        // Arrange - Push items with mixed priorities
        var queueId = $"{fixture.QueueId}-priority-bulk-{Guid.NewGuid():N}";

        // Push priority 1 items first
        await fixture.ApiClient.PostAsJsonAsync($"/queue/{queueId}/push",
            new ApiPushRequest(new List<ApiPushItem> {
                new ApiPushItem(JsonSerializer.SerializeToElement(new { id = 10, priority = 1 }), Priority: 1),
                new ApiPushItem(JsonSerializer.SerializeToElement(new { id = 11, priority = 1 }), Priority: 1)
            }));

        // Push priority 0 items (should come first)
        await fixture.ApiClient.PostAsJsonAsync($"/queue/{queueId}/push",
            new ApiPushRequest(new List<ApiPushItem> {
                new ApiPushItem(JsonSerializer.SerializeToElement(new { id = 0, priority = 0 }), Priority: 0),
                new ApiPushItem(JsonSerializer.SerializeToElement(new { id = 1, priority = 0 }), Priority: 0)
            }));

        // Push priority 2 items (should come last)
        await fixture.ApiClient.PostAsJsonAsync($"/queue/{queueId}/push",
            new ApiPushRequest(new List<ApiPushItem> {
                new ApiPushItem(JsonSerializer.SerializeToElement(new { id = 20, priority = 2 }), Priority: 2)
            }));

        // Act - Bulk pop all items
        var popRequest = new HttpRequestMessage(HttpMethod.Post, $"/queue/{queueId}/pop");
        popRequest.Headers.Add("count", "10");
        var response = await fixture.ApiClient.SendAsync(popRequest);

        // Assert - Priority 0 first, then 1, then 2
        var result = await response.Content.ReadFromJsonAsync<ApiPopResponse>();
        Assert.NotNull(result);
        Assert.Equal(5, result.Items!.Count);

        var actualIds = result.Items.Select(popItem =>
            ((JsonElement)popItem.Item).GetProperty("id").GetInt32()).ToList();
        Assert.Equal(new[] { 0, 1, 10, 11, 20 }, actualIds);
    }

    [Fact]
    public async Task BulkPopWithAck_CreatesMultipleLocks()
    {
        // Arrange - Push 5 items
        var queueId = $"{fixture.QueueId}-bulk-ack-{Guid.NewGuid():N}";

        for (int i = 0; i < 5; i++)
        {
            await fixture.ApiClient.PostAsJsonAsync($"/queue/{queueId}/push",
                new ApiPushRequest(new List<ApiPushItem> {
                    new ApiPushItem(JsonSerializer.SerializeToElement(new { id = i }), Priority: 1)
                }));
        }

        // Act - Bulk pop with acknowledgement
        var popRequest = new HttpRequestMessage(HttpMethod.Post, $"/queue/{queueId}/pop");
        popRequest.Headers.Add("count", "5");
        popRequest.Headers.Add("require_ack", "true");
        popRequest.Headers.Add("ttl_seconds", "30");
        var popResponse = await fixture.ApiClient.SendAsync(popRequest);

        // Assert
        Assert.Equal(HttpStatusCode.OK, popResponse.StatusCode);

        var result = await popResponse.Content.ReadFromJsonAsync<ApiPopWithAckResponse>();
        Assert.NotNull(result);
        Assert.NotNull(result.Items);
        Assert.Equal(5, result.Items.Count);

        // Each lock ID should be unique
        var lockIds = result.Items.Select(item => item.LockId).ToList();
        Assert.Equal(5, lockIds.Distinct().Count());

        // All locks should have expiry times
        Assert.All(result.Items, item =>
            Assert.True(item.LockExpiresAt > DateTimeOffset.UtcNow.ToUnixTimeSeconds()));
    }

    [Fact]
    public async Task BulkPopWithAck_AcknowledgeMultiple_RemovesAllLocks()
    {
        // Arrange - Push and lock 3 items
        var queueId = $"{fixture.QueueId}-bulk-ack-multi-{Guid.NewGuid():N}";

        for (int i = 0; i < 3; i++)
        {
            await fixture.ApiClient.PostAsJsonAsync($"/queue/{queueId}/push",
                new ApiPushRequest(new List<ApiPushItem> {
                    new ApiPushItem(JsonSerializer.SerializeToElement(new { id = i }), Priority: 1)
                }));
        }

        var popRequest = new HttpRequestMessage(HttpMethod.Post, $"/queue/{queueId}/pop");
        popRequest.Headers.Add("count", "3");
        popRequest.Headers.Add("require_ack", "true");
        popRequest.Headers.Add("ttl_seconds", "30");
        var popResponse = await fixture.ApiClient.SendAsync(popRequest);
        var popResult = await popResponse.Content.ReadFromJsonAsync<ApiPopWithAckResponse>();

        Assert.NotNull(popResult);
        Assert.NotNull(popResult.Items);
        Assert.Equal(3, popResult.Items.Count);

        // Act - Acknowledge all locks
        foreach (var item in popResult.Items)
        {
            var ackResponse = await fixture.ApiClient.PostAsJsonAsync($"/queue/{queueId}/acknowledge",
                new ApiAcknowledgeRequest(item.LockId));
            Assert.Equal(HttpStatusCode.OK, ackResponse.StatusCode);
        }

        // Assert - Queue should be empty
        var finalPopRequest = new HttpRequestMessage(HttpMethod.Post, $"/queue/{queueId}/pop");
        finalPopRequest.Headers.Add("count", "10");
        var finalPopResponse = await fixture.ApiClient.SendAsync(finalPopRequest);
        Assert.Equal(HttpStatusCode.NoContent, finalPopResponse.StatusCode);
    }

    [Fact]
    public async Task BulkPop_RequestMoreThanAvailable_ReturnsPartialResults()
    {
        // Arrange - Push only 3 items
        var queueId = $"{fixture.QueueId}-partial-{Guid.NewGuid():N}";

        for (int i = 0; i < 3; i++)
        {
            await fixture.ApiClient.PostAsJsonAsync($"/queue/{queueId}/push",
                new ApiPushRequest(new List<ApiPushItem> {
                    new ApiPushItem(JsonSerializer.SerializeToElement(new { id = i }), Priority: 1)
                }));
        }

        // Act - Request 10 items but only 3 exist
        var popRequest = new HttpRequestMessage(HttpMethod.Post, $"/queue/{queueId}/pop");
        popRequest.Headers.Add("count", "10");
        var response = await fixture.ApiClient.SendAsync(popRequest);

        // Assert - Should return 3 items with 200 OK
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);

        var result = await response.Content.ReadFromJsonAsync<ApiPopResponse>();
        Assert.NotNull(result);
        Assert.NotNull(result.Items);
        Assert.Equal(3, result.Items.Count);
    }

    // gRPC Bulk Pop Tests

    private GrpcService.DaprMQClient CreateGrpcClient()
    {
        AppContext.SetSwitch("System.Net.Http.SocketsHttpHandler.Http2UnencryptedSupport", true);
        var channel = GrpcChannel.ForAddress(fixture.GrpcUrl, new GrpcChannelOptions
        {
            HttpHandler = new SocketsHttpHandler()
        });
        return new GrpcService.DaprMQClient(channel);
    }

    [Fact]
    public async Task BulkPop_Grpc_Count10_ReturnsRepeatedFields()
    {
        // Arrange
        var queueId = $"{fixture.QueueId}-grpc-bulk10-{Guid.NewGuid():N}";
        var client = CreateGrpcClient();

        var pushRequest = new PushRequest { QueueId = queueId };
        for (int i = 0; i < 10; i++)
        {
            pushRequest.Items.Add(new PushItem
            {
                ItemJson = $"{{\"id\":{i}}}",
                Priority = 1
            });
        }
        await client.PushAsync(pushRequest);

        // Act
        var popResponse = await client.PopAsync(new PopRequest
        {
            QueueId = queueId,
            Count = 10
        });

        // Assert
        Assert.Equal(PopResponse.ResultOneofCase.Success, popResponse.ResultCase);
        Assert.Equal(10, popResponse.Success.ItemJson.Count);
        Assert.Equal(10, popResponse.Success.Priority.Count);

        // Verify FIFO order
        for (int i = 0; i < 10; i++)
        {
            Assert.Contains($"\"id\":{i}", popResponse.Success.ItemJson[i]);
        }
    }

    [Fact]
    public async Task BulkPopWithAck_Grpc_ReturnsMultipleLockIds()
    {
        // Arrange
        var queueId = $"{fixture.QueueId}-grpc-bulk-ack-{Guid.NewGuid():N}";
        var client = CreateGrpcClient();

        var pushRequest = new PushRequest { QueueId = queueId };
        for (int i = 0; i < 5; i++)
        {
            pushRequest.Items.Add(new PushItem
            {
                ItemJson = $"{{\"id\":{i}}}",
                Priority = 1
            });
        }
        await client.PushAsync(pushRequest);

        // Act
        var popResponse = await client.PopWithAckAsync(new PopWithAckRequest
        {
            QueueId = queueId,
            TtlSeconds = 30,
            Count = 5
        });

        // Assert
        Assert.Equal(PopWithAckResponse.ResultOneofCase.Success, popResponse.ResultCase);
        Assert.Equal(5, popResponse.Success.ItemJson.Count);
        Assert.Equal(5, popResponse.Success.LockId.Count);
        Assert.Equal(5, popResponse.Success.LockExpiresAt.Count);

        // Each lock ID should be unique
        Assert.Equal(5, popResponse.Success.LockId.Distinct().Count());
    }

    [Fact]
    public async Task BulkPop_Grpc_InvalidCount_ThrowsInvalidArgument()
    {
        // Arrange
        var queueId = $"{fixture.QueueId}-grpc-invalid-count-{Guid.NewGuid():N}";
        var client = CreateGrpcClient();

        // Act & Assert - Count > 100 should throw
        var ex = await Assert.ThrowsAsync<RpcException>(async () =>
            await client.PopAsync(new PopRequest { QueueId = queueId, Count = 101 }));
        Assert.Equal(StatusCode.InvalidArgument, ex.StatusCode);

        // Note: Count = 0 is valid (defaults to 1 in protobuf)
    }
}
