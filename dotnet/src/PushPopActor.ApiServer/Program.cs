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

// Register actors
builder.Services.AddActors(options =>
{
    options.Actors.RegisterActor<PushPopActor.PushPopActor>();
});

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

// Map Dapr actor endpoints
app.MapActorsHandlers();

// Health check endpoint
app.MapGet("/health", () => new { status = "healthy", service = "dapr-push-pop-actor-api-dotnet" });

app.Run();
