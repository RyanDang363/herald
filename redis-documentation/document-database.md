# Redis as a document database quick start guide

```json metadata
{
  "title": "Redis as a document database quick start guide",
  "description": "Understand how to use Redis as a document database",
  "categories": ["docs","develop","stack","oss","rs","rc","oss","kubernetes","clients"],
  "tableOfContents": {"sections":[{"id":"setup","title":"Setup"},{"id":"connect","title":"Connect"},{"id":"create-an-index","title":"Create an index"},{"id":"add-json-documents","title":"Add JSON documents"},{"children":[{"id":"wildcard-query","title":"Wildcard query"},{"id":"single-term-full-text-query","title":"Single-term full-text query"},{"id":"exact-match-query","title":"Exact match query"}],"id":"search-and-query-using-redis-search","title":"Search and query using Redis Search"},{"id":"next-steps","title":"Next steps"},{"id":"continue-learning-with-redis-university","title":"Continue learning with Redis University"}]}

,
  "codeExamples": [{"codetabsId":"search_quickstart-stepconnect","commands":[{"name":"REDIS-CLI"}],"description":"Foundational: Connect to a Redis server using redis-cli with host and port parameters","difficulty":"beginner","id":"connect","languages":[{"id":"redis-cli","panelId":"panel_redis-cli_search_quickstart-stepconnect"},{"clientId":"redis-py","clientName":"redis-py","id":"Python","langId":"python","panelId":"panel_Python_search_quickstart-stepconnect"},{"id":"Node-js","panelId":"panel_Nodejs_search_quickstart-stepconnect"},{"clientId":"jedis","clientName":"Jedis","id":"Java-Sync","langId":"java","panelId":"panel_Java-Sync_search_quickstart-stepconnect"},{"clientId":"go-redis","clientName":"go-redis","id":"Go","langId":"go","panelId":"panel_Go_search_quickstart-stepconnect"},{"id":"dotnet-Sync (NRedisStack)","panelId":"panel_Csharp-Sync (NRedisStack)_search_quickstart-stepconnect"}]},{"codetabsId":"search_quickstart-stepcreate_index","commands":[{"complexity":"O(K)","name":"FT.CREATE"}],"description":"Foundational: Create an index on JSON documents using FT.CREATE with text, numeric, and tag fields","difficulty":"beginner","id":"create_index","languages":[{"id":"redis-cli","panelId":"panel_redis-cli_search_quickstart-stepcreate_index"},{"clientId":"redis-py","clientName":"redis-py","id":"Python","langId":"python","panelId":"panel_Python_search_quickstart-stepcreate_index"},{"id":"Node-js","panelId":"panel_Nodejs_search_quickstart-stepcreate_index"},{"clientId":"jedis","clientName":"Jedis","id":"Java-Sync","langId":"java","panelId":"panel_Java-Sync_search_quickstart-stepcreate_index"},{"clientId":"go-redis","clientName":"go-redis","id":"Go","langId":"go","panelId":"panel_Go_search_quickstart-stepcreate_index"},{"id":"dotnet-Sync (NRedisStack)","panelId":"panel_Csharp-Sync (NRedisStack)_search_quickstart-stepcreate_index"}]},{"codetabsId":"search_quickstart-stepadd_documents","commands":[{"complexity":"O(M+N)","name":"JSON.SET"}],"description":"Foundational: Add JSON documents to Redis using JSON.SET","difficulty":"beginner","id":"add_documents","languages":[{"id":"redis-cli","panelId":"panel_redis-cli_search_quickstart-stepadd_documents"},{"clientId":"redis-py","clientName":"redis-py","id":"Python","langId":"python","panelId":"panel_Python_search_quickstart-stepadd_documents"},{"id":"Node-js","panelId":"panel_Nodejs_search_quickstart-stepadd_documents"},{"clientId":"jedis","clientName":"Jedis","id":"Java-Sync","langId":"java","panelId":"panel_Java-Sync_search_quickstart-stepadd_documents"},{"clientId":"go-redis","clientName":"go-redis","id":"Go","langId":"go","panelId":"panel_Go_search_quickstart-stepadd_documents"},{"id":"dotnet-Sync (NRedisStack)","panelId":"panel_Csharp-Sync (NRedisStack)_search_quickstart-stepadd_documents"}]},{"codetabsId":"search_quickstart-stepwildcard_query","commands":[{"complexity":"O(N)","name":"FT.SEARCH"}],"description":"Foundational: Retrieve all indexed documents using FT.SEARCH with wildcard query","difficulty":"beginner","id":"wildcard_query","languages":[{"id":"redis-cli","panelId":"panel_redis-cli_search_quickstart-stepwildcard_query"},{"clientId":"redis-py","clientName":"redis-py","id":"Python","langId":"python","panelId":"panel_Python_search_quickstart-stepwildcard_query"},{"id":"Node-js","panelId":"panel_Nodejs_search_quickstart-stepwildcard_query"},{"clientId":"jedis","clientName":"Jedis","id":"Java-Sync","langId":"java","panelId":"panel_Java-Sync_search_quickstart-stepwildcard_query"},{"clientId":"go-redis","clientName":"go-redis","id":"Go","langId":"go","panelId":"panel_Go_search_quickstart-stepwildcard_query"},{"id":"dotnet-Sync (NRedisStack)","panelId":"panel_Csharp-Sync (NRedisStack)_search_quickstart-stepwildcard_query"}]},{"codetabsId":"search_quickstart-stepquery_single_term","commands":[{"complexity":"O(N)","name":"FT.SEARCH"}],"description":"Foundational: Perform a single-term full-text query using FT.SEARCH to find documents matching a specific field value","difficulty":"beginner","id":"query_single_term","languages":[{"id":"redis-cli","panelId":"panel_redis-cli_search_quickstart-stepquery_single_term"},{"clientId":"redis-py","clientName":"redis-py","id":"Python","langId":"python","panelId":"panel_Python_search_quickstart-stepquery_single_term"},{"id":"Node-js","panelId":"panel_Nodejs_search_quickstart-stepquery_single_term"},{"clientId":"jedis","clientName":"Jedis","id":"Java-Sync","langId":"java","panelId":"panel_Java-Sync_search_quickstart-stepquery_single_term"},{"clientId":"go-redis","clientName":"go-redis","id":"Go","langId":"go","panelId":"panel_Go_search_quickstart-stepquery_single_term"},{"id":"dotnet-Sync (NRedisStack)","panelId":"panel_Csharp-Sync (NRedisStack)_search_quickstart-stepquery_single_term"}]},{"codetabsId":"search_quickstart-stepquery_exact_matching","commands":[{"complexity":"O(N)","name":"FT.SEARCH"}],"description":"Foundational: Perform an exact match query using FT.SEARCH with double quotes to find documents with precise field values","difficulty":"beginner","id":"query_exact_matching","languages":[{"id":"redis-cli","panelId":"panel_redis-cli_search_quickstart-stepquery_exact_matching"},{"clientId":"redis-py","clientName":"redis-py","id":"Python","langId":"python","panelId":"panel_Python_search_quickstart-stepquery_exact_matching"},{"id":"Node-js","panelId":"panel_Nodejs_search_quickstart-stepquery_exact_matching"},{"clientId":"jedis","clientName":"Jedis","id":"Java-Sync","langId":"java","panelId":"panel_Java-Sync_search_quickstart-stepquery_exact_matching"},{"clientId":"go-redis","clientName":"go-redis","id":"Go","langId":"go","panelId":"panel_Go_search_quickstart-stepquery_exact_matching"},{"id":"dotnet-Sync (NRedisStack)","panelId":"panel_Csharp-Sync (NRedisStack)_search_quickstart-stepquery_exact_matching"}]}]
}
```## Code Examples Legend

The code examples below show how to perform the same operations in different programming languages and client libraries:

- **Redis CLI**: Command-line interface for Redis
- **C# (Synchronous)**: StackExchange.Redis synchronous client
- **C# (Asynchronous)**: StackExchange.Redis asynchronous client
- **Go**: go-redis client
- **Java (Synchronous - Jedis)**: Jedis synchronous client
- **Java (Asynchronous - Lettuce)**: Lettuce asynchronous client
- **Java (Reactive - Lettuce)**: Lettuce reactive/streaming client
- **JavaScript (Node.js)**: node-redis client
- **PHP**: Predis client
- **Python**: redis-py client
- **Rust (Synchronous)**: redis-rs synchronous client
- **Rust (Asynchronous)**: redis-rs asynchronous client

Each code example demonstrates the same basic operation across different languages. The specific syntax and patterns vary based on the language and client library, but the underlying Redis commands and behavior remain consistent.

---



This quick start guide shows you how to:

1. Create a secondary index
2. Add [JSON](https://redis.io/docs/latest/develop/data-types/json/) documents
3. Search and query your data

The examples in this article refer to a simple bicycle inventory that contains JSON documents with the following structure:

```json
{
  "brand": "brand name",
  "condition": "new | used | refurbished",
  "description": "description",
  "model": "model",
  "price": 0
}
```

## Setup

The easiest way to get started with [Redis](https://redis.io/docs/latest/operate/oss_and_stack/) is to use Redis Cloud:

1. Create a [free account](https://redis.com/try-free?utm_source=redisio&utm_medium=referral&utm_campaign=2023-09-try_free&utm_content=cu-redis_cloud_users).

   <img src="../img/free-cloud-db.png" width="500px">
2. Follow the instructions to create a free database.

This free Redis Cloud database comes out of the box with all the Redis Open Source features.

You can alternatively use the [installation guides](https://redis.io/docs/latest/operate/oss_and_stack/install/install-stack/) to install Redis Open Source on your local machine.


## Connect

The first step is to connect to your Redis Open Source database. You can find further details about the connection options in this documentation site's [Tools section](https://redis.io/docs/latest/develop/tools). The following example shows how to connect to a Redis Open Source server that runs on localhost (`-h 127.0.0.1`) and listens on the default port (`-p 6379`): 

Foundational: Connect to a Redis server using redis-cli with host and port parameters

**Difficulty:** Beginner

**Commands:** REDIS-CLI

**Available in:** Redis CLI, C#, Go, Java (Synchronous - Jedis), JavaScript (Node.js), Python

##### Redis CLI

```
> redis-cli -h 127.0.0.1 -p 6379
```

##### C#

```csharp
        var muxer = ConnectionMultiplexer.Connect("localhost:6379");
        var db = muxer.GetDatabase();
        var ft = db.FT();
        var json = db.JSON();
```

##### Go

```go
	ctx := context.Background()

	rdb := redis.NewClient(&redis.Options{
		Addr:     "localhost:6379",
		Password: "", // no password docs
		DB:       0,  // use default DB
		Protocol: 2,
	})
```

##### Java (Synchronous - Jedis)

```java
    RedisClient jedis = RedisClient.create("localhost", 6379);
```

##### JavaScript (Node.js)

```javascript
const client = createClient();
client.on('error', err => console.log('Redis Client Error', err));

await client.connect();
```

##### Python

```python
r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
```



<br/>

You can copy and paste the connection details from the Redis Cloud database configuration page. Here is an example connection string of a Cloud database that is hosted in the AWS region `us-east-1` and listens on port 16379: `redis-16379.c283.us-east-1-4.ec2.cloud.redislabs.com:16379`. The connection string has the format `host:port`. You must also copy and paste your Cloud database's username and password and then pass the credentials to your client or use the [AUTH command](https://redis.io/docs/latest/commands/auth) after the connection is established.



## Create an index

As explained in the [in-memory data store](https://redis.io/docs/latest/develop/get-started/data-store) quick start guide, Redis allows you to access an item directly via its key. You also learned how to scan the keyspace. Whereby you can use other data structures (e.g., hashes and sorted sets) as secondary indexes, your application would need to maintain those indexes manually. Redis is a document database that allows you to declare which fields are auto-indexed. Redis currently supports secondary index creation on the [hashes](https://redis.io/docs/latest/develop/data-types/hashes) and [JSON](https://redis.io/docs/latest/develop/data-types/json) documents.

The following example shows an [FT.CREATE](https://redis.io/docs/latest/commands/ft.create) command that creates an index with some text fields, a numeric field (price), and a tag field (condition). The text fields have a weight of 1.0, meaning they have the same relevancy in the context of full-text searches. The field names follow the [JSONPath](https://redis.io/docs/latest/develop/data-types/json/path) notion. Each such index field maps to a property within the JSON document.


Foundational: Create an index on JSON documents using FT.CREATE with text, numeric, and tag fields

**Difficulty:** Beginner

**Commands:** FT.CREATE

**Complexity:**
- FT.CREATE: O(K)

**Available in:** Redis CLI, C#, Go, Java (Synchronous - Jedis), JavaScript (Node.js), Python

##### Redis CLI

```
> FT.CREATE idx:bicycle ON JSON PREFIX 1 bicycle: SCORE 1.0 SCHEMA $.brand AS brand TEXT WEIGHT 1.0 $.model AS model TEXT WEIGHT 1.0 $.description AS description TEXT WEIGHT 1.0 $.price AS price NUMERIC $.condition AS condition TAG SEPARATOR ,
OK
```

##### C#

```csharp
        var schema = new Schema()
            .AddTextField(new FieldName("$.Brand", "Brand"))
            .AddTextField(new FieldName("$.Model", "Model"))
            .AddTextField(new FieldName("$.Description", "Description"))
            .AddNumericField(new FieldName("$.Price", "Price"))
            .AddTagField(new FieldName("$.Condition", "Condition"));

        ft.Create(
            "idx:bicycle",
            new FTCreateParams().On(IndexDataType.JSON).Prefix("bicycle:"),
            schema);
```

##### Go

```go
	schema := []*redis.FieldSchema{
		{
			FieldName: "$.brand",
			As:        "brand",
			FieldType: redis.SearchFieldTypeText,
		},
		{
			FieldName: "$.model",
			As:        "model",
			FieldType: redis.SearchFieldTypeText,
		},
		{
			FieldName: "$.description",
			As:        "description",
			FieldType: redis.SearchFieldTypeText,
		},
	}

	_, err := rdb.FTCreate(ctx, "idx:bicycle",
		&redis.FTCreateOptions{
			Prefix: []interface{}{"bicycle:"},
			OnJSON: true,
		},
		schema...,
	).Result()

	if err != nil {
		panic(err)
	}
```

##### Java (Synchronous - Jedis)

```java
    SchemaField[] schema = {
      TextField.of("$.brand").as("brand"),
      TextField.of("$.model").as("model"),
      TextField.of("$.description").as("description"),
      NumericField.of("$.price").as("price"),
      TagField.of("$.condition").as("condition")
    };

    jedis.ftCreate("idx:bicycle",
      FTCreateParams.createParams()
      .on(IndexDataType.JSON)
      .addPrefix("bicycle:"),
      schema
    );
```

##### JavaScript (Node.js)

```javascript
const schema = {
  '$.brand': {
    type: SCHEMA_FIELD_TYPE.TEXT,
    SORTABLE: true,
    AS: 'brand'
  },
  '$.model': {
    type: SCHEMA_FIELD_TYPE.TEXT,
    AS: 'model'
  },
  '$.description': {
    type: SCHEMA_FIELD_TYPE.TEXT,
    AS: 'description'
  },
  '$.price': {
    type: SCHEMA_FIELD_TYPE.NUMERIC,
    AS: 'price'
  },
  '$.condition': {
    type: SCHEMA_FIELD_TYPE.TAG,
    AS: 'condition'
  }
};

try {
  await client.ft.create('idx:bicycle', schema, {
    ON: 'JSON',
    PREFIX: 'bicycle:'
  });
} catch (e) {
  if (e.message === 'Index already exists') {
    console.log('Index exists already, skipped creation.');
  } else {
    // Something went wrong, perhaps RediSearch isn't installed...
    console.error(e);
    process.exit(1);
  }
}
```

##### Python

```python
schema = (
    TextField("$.brand", as_name="brand"),
    TextField("$.model", as_name="model"),
    TextField("$.description", as_name="description"),
    NumericField("$.price", as_name="price"),
    TagField("$.condition", as_name="condition"),
)

index = r.ft("idx:bicycle")
index.create_index(
    schema,
    definition=IndexDefinition(prefix=["bicycle:"], index_type=IndexType.JSON),
)
```



Any pre-existing JSON documents with a key prefix `bicycle:` are automatically added to the index. Additionally, any JSON documents with that prefix created or modified after index creation are added or re-added to the index.

## Add JSON documents

The example below shows you how to use the [JSON.SET](https://redis.io/docs/latest/commands/json.set) command to create new JSON documents:

Foundational: Add JSON documents to Redis using JSON.SET

**Difficulty:** Beginner

**Commands:** JSON.SET

**Complexity:**
- JSON.SET: O(M+N)

**Available in:** Redis CLI, C#, Go, Java (Synchronous - Jedis), JavaScript (Node.js), Python

##### Redis CLI

```
> JSON.SET "bicycle:0" "." "{\"brand\": \"Velorim\", \"model\": \"Jigger\", \"price\": 270, \"description\": \"Small and powerful, the Jigger is the best ride for the smallest of tikes! This is the tiniest kids\\u2019 pedal bike on the market available without a coaster brake, the Jigger is the vehicle of choice for the rare tenacious little rider raring to go.\", \"condition\": \"new\"}"
... output truncated for AI-facing Markdown ...
> JSON.SET "bicycle:9" "." "{\"model\": \"ThrillCycle\", \"brand\": \"BikeShind\", \"price\": 815, \"description\": \"An artsy,  retro-inspired bicycle that\\u2019s as functional as it is pretty: The ThrillCycle steel frame offers a smooth ride. A 9-speed drivetrain has enough gears for coasting in the city, but we wouldn\\u2019t suggest taking it to the mountains. Fenders protect you from mud, and a rear basket lets you transport groceries, flowers and books. The ThrillCycle comes with a limited lifetime warranty, so this little guy will last you long past graduation.\", \"condition\": \"refurbished\"}"
OK
```

##### C#

```csharp
        for (int i = 0; i < bicycles.Length; i++)
        {
            json.Set($"bicycle:{i}", "$", bicycles[i]);
        }
```

##### Go

```go
	for i, bicycle := range bicycles {
		_, err := rdb.JSONSet(
			ctx,
			fmt.Sprintf("bicycle:%v", i),
			"$",
			bicycle,
		).Result()

		if err != nil {
			panic(err)
		}
	}
```

##### Java (Synchronous - Jedis)

```java
    for (int i = 0; i < bicycles.length; i++) {
      jedis.jsonSetWithEscape(String.format("bicycle:%d", i), bicycles[i]);
    }
```

##### JavaScript (Node.js)

```javascript
await Promise.all(
  bicycles.map((bicycle, i) => client.json.set(`bicycle:${i}`, '$', bicycle))
);
```

##### Python

```python
for bid, bicycle in enumerate(bicycles):
    r.json().set(f"bicycle:{bid}", Path.root_path(), bicycle)
```



## Search and query using Redis Search

### Wildcard query

You can retrieve all indexed documents using the [FT.SEARCH](https://redis.io/docs/latest/commands/ft.search) command. Note the `LIMIT` clause below, which allows result pagination.

Foundational: Retrieve all indexed documents using FT.SEARCH with wildcard query

**Difficulty:** Beginner

**Commands:** FT.SEARCH

**Complexity:**
- FT.SEARCH: O(N)

**Available in:** Redis CLI, C#, Go, Java (Synchronous - Jedis), JavaScript (Node.js), Python

##### Redis CLI

```
> FT.SEARCH "idx:bicycle" "*" LIMIT 0 10
1) (integer) 10
 2) "bicycle:1"
 3) 1) "$"
    2) "{\"brand\":\"Bicyk\",\"model\":\"Hillcraft\",\"price\":1200,\"description\":\"Kids want to ride with as little weight as possible. Especially on an incline! They may be at the age when a 27.5\\\" wheel bike is just too clumsy coming off a 24\\\" bike. The Hillcraft 26 is just the solution they need!\",\"condition\":\"used\"}"
 4) "bicycle:2"
 5) 1) "$"
    2) "{\"brand\":\"Nord\",\"model\":\"Chook air 5\",\"price\":815,\"description\":\"The Chook Air 5  gives kids aged six years and older a durable and uberlight mountain bike for their first experience on tracks and easy cruising through forests and fields. The lower  top tube makes it easy to mount and dismount in any situation, giving your kids greater safety on the trails.\",\"condition\":\"used\"}"
... output truncated for AI-facing Markdown ...
20) "bicycle:8"
21) 1) "$"
    2) "{\"brand\":\"nHill\",\"model\":\"Summit\",\"price\":1200,\"description\":\"This budget mountain bike from nHill performs well both on bike paths and on the trail. The fork with 100mm of travel absorbs rough terrain. Fat Kenda Booster tires give you grip in corners and on wet trails. The Shimano Tourney drivetrain offered enough gears for finding a comfortable pace to ride uphill, and the Tektro hydraulic disc brakes break smoothly. Whether you want an affordable bike that you can take to work, but also take trail in mountains on the weekends or you\xe2\x80\x99re just after a stable, comfortable ride for the bike path, the Summit gives a good value for money.\",\"condition\":\"new\"}"
```

##### C#

```csharp
        var query1 = new Query("*");
        var res1 = ft.Search("idx:bicycle", query1).Documents;
        Console.WriteLine(string.Join("\n", res1.Count()));
        // Prints: Documents found: 10
```

##### Go

```go
	wCardResult, err := rdb.FTSearch(ctx, "idx:bicycle", "*").Result()

	if err != nil {
		panic(err)
	}

	fmt.Printf("Documents found: %v\n", wCardResult.Total)
	// >>> Documents found: 10
```

##### Java (Synchronous - Jedis)

```java
    Query query1 = new Query("*");
    List<Document> result1 = jedis.ftSearch("idx:bicycle", query1).getDocuments();
    System.out.println("Documents found:" + result1.size());
    // Prints: Documents found: 10
```

##### JavaScript (Node.js)

```javascript
let result = await client.ft.search('idx:bicycle', '*', {
  LIMIT: {
    from: 0,
    size: 10
  }
});

console.log(JSON.stringify(result, null, 2));

/*
{
  "total": 10,
  "documents": ...
}
*/
```

##### Python

```python
res = index.search(Query("*"))
print("Documents found:", res.total)
# >>> Documents found: 10
```



### Single-term full-text query

The following command shows a simple single-term query for finding all bicycles with a specific model:

Foundational: Perform a single-term full-text query using FT.SEARCH to find documents matching a specific field value

**Difficulty:** Beginner

**Commands:** FT.SEARCH

**Complexity:**
- FT.SEARCH: O(N)

**Available in:** Redis CLI, C#, Go, Java (Synchronous - Jedis), JavaScript (Node.js), Python

##### Redis CLI

```
> FT.SEARCH "idx:bicycle" "@model:Jigger" LIMIT 0 10
1) (integer) 1
2) "bicycle:0"
3) 1) "$"
   2) "{\"brand\":\"Velorim\",\"model\":\"Jigger\",\"price\":270,\"description\":\"Small and powerful, the Jigger is the best ride for the smallest of tikes! This is the tiniest kids\xe2\x80\x99 pedal bike on the market available without a coaster brake, the Jigger is the vehicle of choice for the rare tenacious little rider raring to go.\",\"condition\":\"new\"}"
```

##### C#

```csharp
        var query2 = new Query("@Model:Jigger");
        var res2 = ft.Search("idx:bicycle", query2).Documents;
        Console.WriteLine(string.Join("\n", res2.Select(x => x["json"])));
        // Prints: {"Brand":"Moore PLC","Model":"Award Race","Price":3790.76,
        //          "Description":"This olive folding bike features a carbon frame
        //          and 27.5 inch wheels. This folding bike is perfect for compact
        //          storage and transportation.","Condition":"new"}
```

##### Go

```go
	stResult, err := rdb.FTSearch(
		ctx,
		"idx:bicycle",
		"@model:Jigger",
	).Result()

	if err != nil {
		panic(err)
	}

	fmt.Println(stResult)
	// >>> {1 [{bicycle:0 <nil> <nil> <nil> map[$:{"brand":"Velorim", ...
```

##### Java (Synchronous - Jedis)

```java
    Query query2 = new Query("@model:Jigger");
    List<Document> result2 = jedis.ftSearch("idx:bicycle", query2).getDocuments();
    System.out.println(result2);
    // Prints: [id:bicycle:0, score: 1.0, payload:null,
    // properties:[$={"brand":"Velorim","model":"Jigger","price":270,"description":"Small and powerful, the Jigger is the best ride for the smallest of tikes! This is the tiniest kids’ pedal bike on the market available without a coaster brake, the Jigger is the vehicle of choice for the rare tenacious little rider raring to go.","condition":"new"}]]
```

##### JavaScript (Node.js)

```javascript
result = await client.ft.search(
  'idx:bicycle',
  '@model:Jigger',
  {
    LIMIT: {
    from: 0,
    size: 10
  }
});

console.log(JSON.stringify(result, null, 2));
/*
{
  "total": 1,
  "documents": [{
    "id": "bicycle:0",
    "value": {
      "brand": "Velorim",
      "model": "Jigger",
      "price": 270,
      "description": "Small and powerful, the Jigger is the best ride for the smallest of tikes! This is the tiniest kids’ pedal bike on the market available without a coaster brake, the Jigger is the vehicle of choice for the rare tenacious little rider raring to go.",
      "condition": "new"
    }
  }]
}
 */
```

##### Python

```python
res = index.search(Query("@model:Jigger"))
print(res)
# >>> Result{1 total, docs: [
# Document {
#   'id': 'bicycle:0',
#   'payload': None,
#   'json': '{
#       "brand":"Velorim",
#       "model":"Jigger",
#       "price":270,
#       ...
#       "condition":"new"
#    }'
# }]}
```



### Exact match query

Below is a command to perform an exact match query that finds all bicycles with the brand name `Noka Bikes`. You must use double quotes around the search term when constructing an exact match query on a  text field.

Foundational: Perform an exact match query using FT.SEARCH with double quotes to find documents with precise field values

**Difficulty:** Beginner

**Commands:** FT.SEARCH

**Complexity:**
- FT.SEARCH: O(N)

**Available in:** Redis CLI, C#, Go, Java (Synchronous - Jedis), JavaScript (Node.js), Python

##### Redis CLI

```
> FT.SEARCH "idx:bicycle" "@brand:\"Noka Bikes\"" LIMIT 0 10
1) (integer) 1
2) "bicycle:4"
3) 1) "$"
   2) "{\"brand\":\"Noka Bikes\",\"model\":\"Kahuna\",\"price\":3200,\"description\":\"Whether you want to try your hand at XC racing or are looking for a lively trail bike that's just as inspiring on the climbs as it is over rougher ground, the Wilder is one heck of a bike built specifically for short women. Both the frames and components have been tweaked to include a women\xe2\x80\x99s saddle, different bars and unique colourway.\",\"condition\":\"used\"}"
```

##### C#

```csharp
        var query4 = new Query("@Brand:\"Noka Bikes\"");
        var res4 = ft.Search("idx:bicycle", query4).Documents;
        Console.WriteLine(string.Join("\n", res4.Select(x => x["json"])));
        // Prints: {"Brand":"Moore PLC","Model":"Award Race","Price":3790.76,
        //          "Description":"This olive folding bike features a carbon frame
        //          and 27.5 inch wheels. This folding bike is perfect for compact
        //          storage and transportation.","Condition":"new"}
```

##### Go

```go
	exactMatchResult, err := rdb.FTSearch(
		ctx,
		"idx:bicycle",
		"@brand:\"Noka Bikes\"",
	).Result()

	if err != nil {
		panic(err)
	}

	fmt.Println(exactMatchResult)
	// >>> {1 [{bicycle:4 <nil> <nil> <nil> map[$:{"brand":"Noka Bikes"...
```

##### Java (Synchronous - Jedis)

```java
    Query query5 = new Query("@brand:\"Noka Bikes\"");
    List<Document> result5 = jedis.ftSearch("idx:bicycle", query5).getDocuments();
    System.out.println(result5);
    // Prints: [id:bicycle:4, score: 1.0, payload:null,
    // properties:[$={"brand":"Noka Bikes","model":"Kahuna","price":3200,"description":"Whether you want to try your hand at XC racing or are looking for a lively trail bike that's just as inspiring on the climbs as it is over rougher ground, the Wilder is one heck of a bike built specifically for short women. Both the frames and components have been tweaked to include a women’s saddle, different bars and unique colourway.","condition":"used"}]]
```

##### JavaScript (Node.js)

```javascript
result = await client.ft.search(
  'idx:bicycle',
  '@brand:"Noka Bikes"',
  {
    LIMIT: {
      from: 0,
      size: 10
    }
  }
);

console.log(JSON.stringify(result, null, 2));

/*
{
  "total": 1,
  "documents": [{
    "id": "bicycle:4",
    "value": {
      "brand": "Noka Bikes",
      "model": "Kahuna",
      "price": 3200,
      "description": "Whether you want to try your hand at XC racing or are looking for a lively trail bike that's just as inspiring on the climbs as it is over rougher ground, the Wilder is one heck of a bike built specifically for short women. Both the frames and components have been tweaked to include a women’s saddle, different bars and unique colourway.",
      "condition": "used"
    }
  }]
}
*/
```

##### Python

```python
res = index.search(Query('@brand:"Noka Bikes"'))
print(res)
# >>> Result{1 total, docs: [
# Document {
#   'id': 'bicycle:4',
#   'payload': None,
#   'json': '{
#       "brand":"Noka Bikes",
#       "model":"Kahuna",
#       "price":3200,
#       ...
#       "condition":"used"
#    }'
# }]}
```



Please see the [query documentation](https://redis.io/docs/latest/develop/ai/search-and-query/query/) to learn how to make more advanced queries.

## Next steps

You can learn more about how to use Redis Open Source as a vector database in the following quick start guide:

* [Redis as a vector database](https://redis.io/docs/latest/develop/get-started/vector-database)

## Continue learning with Redis University


