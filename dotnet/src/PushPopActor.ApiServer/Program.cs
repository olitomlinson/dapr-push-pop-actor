using System.Text.Json;
using System.Text.Json.Serialization;
using Dapr.Actors;
using Dapr.Actors.Client;
using Dapr.Actors.Runtime;

var builder = WebApplication.CreateBuilder(args);

// Add services to the container
builder.Services.AddControllers().AddDapr();

// Add Swagger/OpenAPI
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen(c =>
{
    c.SwaggerDoc("v1", new() { Title = "Dapr Push-Pop Actor API (.NET)", Version = "v1" });
});

// Register actors (conditionally based on environment variable)
var registerActors = builder.Configuration.GetValue<bool>("REGISTER_ACTORS", true);
if (registerActors)
{
    builder.Services.AddActors(options =>
    {
        options.Actors.RegisterActor<PushPopActor.PushPopActor>();

        // Configure actor runtime settings
        options.ActorIdleTimeout = TimeSpan.FromSeconds(60);
        options.JsonSerializerOptions = new JsonSerializerOptions
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase, // Use camelCase instead of PascalCase
            DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull, // Skip null properties
            WriteIndented = false // Set to true only for debugging
        };
    });
}
// No else needed - Dapr Client (from AddDapr) is sufficient for actor invocation

var app = builder.Build();

// Configure the HTTP request pipeline
if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseRouting();
app.UseAuthorization();

// Map controllers
app.MapControllers();

// Map Dapr actor endpoints (only needed when hosting actors)
if (registerActors)
{
    app.MapActorsHandlers();
}

// Health check endpoint
app.MapGet("/health", () => new { status = "healthy", service = "dapr-push-pop-actor-api-dotnet" });

app.Run();
