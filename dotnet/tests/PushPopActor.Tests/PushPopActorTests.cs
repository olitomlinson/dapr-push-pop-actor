using Dapr.Actors.Runtime;
using Moq;
using Xunit;

namespace PushPopActor.Tests;

public class PushPopActorTests
{
    private Mock<IActorStateManager> CreateMockStateManager()
    {
        var mock = new Mock<IActorStateManager>();
        var stateData = new Dictionary<string, object>();

        // Setup GetStateAsync
        mock.Setup(m => m.TryGetStateAsync<Dictionary<string, object>>(It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((string key, CancellationToken ct) =>
            {
                if (stateData.ContainsKey(key))
                {
                    return new ConditionalValue<Dictionary<string, object>>(true, (Dictionary<string, object>)stateData[key]);
                }
                return new ConditionalValue<Dictionary<string, object>>(false, null);
            });

        mock.Setup(m => m.TryGetStateAsync<List<Dictionary<string, object>>>(It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync((string key, CancellationToken ct) =>
            {
                if (stateData.ContainsKey(key))
                {
                    return new ConditionalValue<List<Dictionary<string, object>>>(true, (List<Dictionary<string, object>>)stateData[key]);
                }
                return new ConditionalValue<List<Dictionary<string, object>>>(false, null);
            });

        // Setup SetStateAsync
        mock.Setup(m => m.SetStateAsync(It.IsAny<string>(), It.IsAny<object>(), It.IsAny<CancellationToken>()))
            .Returns((string key, object value, CancellationToken ct) =>
            {
                stateData[key] = value;
                return Task.CompletedTask;
            });

        // Setup RemoveStateAsync
        mock.Setup(m => m.RemoveStateAsync(It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .Returns((string key, CancellationToken ct) =>
            {
                stateData.Remove(key);
                return Task.CompletedTask;
            });

        // Setup SaveStateAsync
        mock.Setup(m => m.SaveStateAsync(It.IsAny<CancellationToken>()))
            .Returns(Task.CompletedTask);

        return mock;
    }

    private PushPopActor CreateActor(Mock<IActorStateManager> mockStateManager)
    {
        var actorHost = ActorHost.CreateForTest<PushPopActor>();
        var actor = new PushPopActor(actorHost);

        // Use reflection to set the StateManager property
        var stateManagerProperty = typeof(Actor).GetProperty("StateManager");
        stateManagerProperty?.SetValue(actor, mockStateManager.Object);

        return actor;
    }

    [Fact]
    public async Task PushAsync_WithValidItem_ReturnsTrue()
    {
        // Arrange
        var mockStateManager = CreateMockStateManager();
        var actor = CreateActor(mockStateManager);
        var itemJson = System.Text.Json.JsonSerializer.Serialize(new Dictionary<string, object> { ["message"] = "test" });
        var request = new Interfaces.PushRequest { ItemJson = itemJson, Priority = 0 };

        // Act
        var result = await actor.Push(request);

        // Assert
        Assert.True(result.Success);
    }

    [Fact]
    public async Task PushAsync_WithoutItem_ReturnsFalse()
    {
        // Arrange
        var mockStateManager = CreateMockStateManager();
        var actor = CreateActor(mockStateManager);
        var request = new Interfaces.PushRequest { ItemJson = "", Priority = 0 };

        // Act
        var result = await actor.Push(request);

        // Assert
        Assert.False(result.Success);
    }

    [Fact]
    public async Task PushAsync_WithNegativePriority_ReturnsFalse()
    {
        // Arrange
        var mockStateManager = CreateMockStateManager();
        var actor = CreateActor(mockStateManager);
        var itemJson = System.Text.Json.JsonSerializer.Serialize(new Dictionary<string, object> { ["message"] = "test" });
        var request = new Interfaces.PushRequest { ItemJson = itemJson, Priority = -1 };

        // Act
        var result = await actor.Push(request);

        // Assert
        Assert.False(result.Success);
    }

    [Fact]
    public async Task PopAsync_FromEmptyQueue_ReturnsEmptyList()
    {
        // Arrange
        var mockStateManager = CreateMockStateManager();
        var actor = CreateActor(mockStateManager);

        // Act
        var result = await actor.Pop();

        // Assert
        Assert.Empty(result.ItemsJson);
    }

    [Fact]
    public async Task PopAsync_AfterPush_ReturnsItem()
    {
        // Arrange
        var mockStateManager = CreateMockStateManager();
        var actor = CreateActor(mockStateManager);
        var itemJson = System.Text.Json.JsonSerializer.Serialize(new Dictionary<string, object> { ["message"] = "test" });
        var pushRequest = new Interfaces.PushRequest { ItemJson = itemJson, Priority = 0 };

        // Act
        await actor.Push(pushRequest);
        var result = await actor.Pop();

        // Assert
        Assert.Single(result.ItemsJson);
        var returnedItem = System.Text.Json.JsonSerializer.Deserialize<Dictionary<string, object>>(result.ItemsJson[0]);
        Assert.Equal("test", returnedItem!["message"].ToString());
    }

    [Fact]
    public async Task PushPop_MaintainsFIFOOrder()
    {
        // Arrange
        var mockStateManager = CreateMockStateManager();
        var actor = CreateActor(mockStateManager);

        // Act - Push 3 items
        await actor.Push(new Interfaces.PushRequest
        {
            ItemJson = System.Text.Json.JsonSerializer.Serialize(new Dictionary<string, object> { ["id"] = 1 }),
            Priority = 0
        });
        await actor.Push(new Interfaces.PushRequest
        {
            ItemJson = System.Text.Json.JsonSerializer.Serialize(new Dictionary<string, object> { ["id"] = 2 }),
            Priority = 0
        });
        await actor.Push(new Interfaces.PushRequest
        {
            ItemJson = System.Text.Json.JsonSerializer.Serialize(new Dictionary<string, object> { ["id"] = 3 }),
            Priority = 0
        });

        // Pop all items
        var item1 = await actor.Pop();
        var item2 = await actor.Pop();
        var item3 = await actor.Pop();

        // Assert - Should be in FIFO order
        var deserialized1 = System.Text.Json.JsonSerializer.Deserialize<Dictionary<string, object>>(item1.ItemsJson[0]);
        var deserialized2 = System.Text.Json.JsonSerializer.Deserialize<Dictionary<string, object>>(item2.ItemsJson[0]);
        var deserialized3 = System.Text.Json.JsonSerializer.Deserialize<Dictionary<string, object>>(item3.ItemsJson[0]);

        Assert.Equal(1, Convert.ToInt32(deserialized1!["id"].ToString()));
        Assert.Equal(2, Convert.ToInt32(deserialized2!["id"].ToString()));
        Assert.Equal(3, Convert.ToInt32(deserialized3!["id"].ToString()));
    }

    [Fact]
    public async Task PopWithAckAsync_CreatesLock()
    {
        // Arrange
        var mockStateManager = CreateMockStateManager();
        var actor = CreateActor(mockStateManager);
        var itemJson = System.Text.Json.JsonSerializer.Serialize(new Dictionary<string, object> { ["message"] = "test" });
        await actor.Push(new Interfaces.PushRequest { ItemJson = itemJson, Priority = 0 });

        // Act
        var result = await actor.PopWithAck(new Interfaces.PopWithAckRequest { TtlSeconds = 30 });

        // Assert
        Assert.True(result.Locked);
        Assert.NotNull(result.LockId);
        Assert.Single(result.ItemsJson);
    }

    [Fact]
    public async Task AcknowledgeAsync_WithValidLockId_ReturnsSuccess()
    {
        // Arrange
        var mockStateManager = CreateMockStateManager();
        var actor = CreateActor(mockStateManager);
        var itemJson = System.Text.Json.JsonSerializer.Serialize(new Dictionary<string, object> { ["message"] = "test" });
        await actor.Push(new Interfaces.PushRequest { ItemJson = itemJson, Priority = 0 });

        var popResult = await actor.PopWithAck(new Interfaces.PopWithAckRequest { TtlSeconds = 30 });
        var lockId = popResult.LockId!;

        // Act
        var ackResult = await actor.Acknowledge(new Interfaces.AcknowledgeRequest { LockId = lockId });

        // Assert
        Assert.True(ackResult.Success);
        Assert.Equal(1, ackResult.ItemsAcknowledged);
    }

    [Fact]
    public async Task AcknowledgeAsync_WithInvalidLockId_ReturnsFalse()
    {
        // Arrange
        var mockStateManager = CreateMockStateManager();
        var actor = CreateActor(mockStateManager);

        // Act
        var result = await actor.Acknowledge(new Interfaces.AcknowledgeRequest { LockId = "invalid" });

        // Assert
        Assert.False(result.Success);
        Assert.Equal("LOCK_NOT_FOUND", result.ErrorCode);
    }
}
