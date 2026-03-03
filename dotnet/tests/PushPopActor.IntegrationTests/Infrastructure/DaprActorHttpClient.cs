using System.Text;
using System.Text.Json;

namespace PushPopActor.IntegrationTests.Infrastructure;

/// <summary>
/// Helper class for calling Dapr Actor HTTP API directly
/// Enables interrogation of actor internals for testing
/// </summary>
public class DaprActorHttpClient
{
    private readonly HttpClient _daprClient;
    private const string ActorType = "PushPopActor";

    public DaprActorHttpClient(HttpClient daprClient)
    {
        _daprClient = daprClient ?? throw new ArgumentNullException(nameof(daprClient));
    }

    /// <summary>
    /// Get actor state directly via Dapr HTTP API
    /// GET /v1.0/actors/{actorType}/{actorId}/state/{key}
    /// </summary>
    public async Task<T?> GetActorStateAsync<T>(string actorId, string stateKey)
    {
        var url = $"/v1.0/actors/{ActorType}/{actorId}/state/{stateKey}";
        var response = await _daprClient.GetAsync(url);

        if (response.StatusCode == System.Net.HttpStatusCode.NoContent ||
            response.StatusCode == System.Net.HttpStatusCode.NotFound)
        {
            return default;
        }

        response.EnsureSuccessStatusCode();
        var json = await response.Content.ReadAsStringAsync();
        return JsonSerializer.Deserialize<T>(json);
    }

    /// <summary>
    /// Invoke actor method directly via Dapr HTTP API
    /// POST /v1.0/actors/{actorType}/{actorId}/method/{methodName}
    /// </summary>
    public async Task<TResponse> InvokeActorMethodAsync<TRequest, TResponse>(
        string actorId,
        string methodName,
        TRequest request)
    {
        var url = $"/v1.0/actors/{ActorType}/{actorId}/method/{methodName}";
        var json = JsonSerializer.Serialize(request);
        var content = new StringContent(json, Encoding.UTF8, "application/json");

        var response = await _daprClient.PostAsync(url, content);
        response.EnsureSuccessStatusCode();

        var responseJson = await response.Content.ReadAsStringAsync();
        return JsonSerializer.Deserialize<TResponse>(responseJson)!;
    }

    /// <summary>
    /// Invoke actor method with no request body
    /// POST /v1.0/actors/{actorType}/{actorId}/method/{methodName}
    /// </summary>
    public async Task<TResponse> InvokeActorMethodAsync<TResponse>(
        string actorId,
        string methodName)
    {
        var url = $"/v1.0/actors/{ActorType}/{actorId}/method/{methodName}";
        var response = await _daprClient.PostAsync(url, null);
        response.EnsureSuccessStatusCode();

        var responseJson = await response.Content.ReadAsStringAsync();
        return JsonSerializer.Deserialize<TResponse>(responseJson)!;
    }
}
