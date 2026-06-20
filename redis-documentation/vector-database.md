# Redis as a vector database quick start guide

```json metadata
{
  "title": "Redis as a vector database quick start guide",
  "description": "Understand how to use Redis as a vector database",
  "categories": ["docs","develop","stack","oss","rs","rc","oss","kubernetes","clients"],
  "tableOfContents": {"sections":[{"id":"understand-vector-databases","title":"Understand vector databases"},{"id":"create-a-redis-vector-database","title":"Create a Redis vector database"},{"id":"install-the-required-python-packages","title":"Install the required Python packages"},{"id":"connect","title":"Connect"},{"children":[{"id":"1-fetch-the-demo-data","title":"1. Fetch the demo data"},{"id":"2-store-the-demo-data-in-redis","title":"2. Store the demo data in Redis"},{"id":"3-select-a-text-embedding-model","title":"3. Select a text embedding model"},{"id":"4-generate-text-embeddings","title":"4. Generate text embeddings"}],"id":"prepare-the-demo-dataset","title":"Prepare the demo dataset"},{"children":[{"id":"1-create-an-index-with-a-vector-field","title":"1. Create an index with a vector field"},{"id":"2-check-the-state-of-the-index","title":"2. Check the state of the index"}],"id":"create-an-index","title":"Create an index"},{"children":[{"id":"1-embed-your-queries","title":"1. Embed your queries"},{"id":"2-k-nearest-neighbors-knn-search","title":"2. K-nearest neighbors (KNN) search"}],"id":"perform-vector-searches","title":"Perform vector searches"},{"id":"next-steps","title":"Next steps"},{"id":"continue-learning-with-redis-university","title":"Continue learning with Redis University"}]}

,
  "codeExamples": [{"codetabsId":"search_vss-stepimports","description":"Foundational: Import required Python packages for vector database operations including redis, pandas, and sentence-transformers","difficulty":"beginner","id":"imports","languages":[{"clientId":"redis-py","clientName":"redis-py","id":"Python","langId":"python","panelId":"panel_Python_search_vss-stepimports"}]},{"codetabsId":"search_vss-stepconnect","description":"Foundational: Connect to a Redis server with decode_responses enabled to receive decoded strings instead of bytes","difficulty":"beginner","id":"connect","languages":[{"clientId":"redis-py","clientName":"redis-py","id":"Python","langId":"python","panelId":"panel_Python_search_vss-stepconnect"}]},{"codetabsId":"search_vss-stepget_data","description":"Foundational: Fetch the demo dataset as a JSON array to prepare data for vector database operations","difficulty":"beginner","id":"get_data","languages":[{"clientId":"redis-py","clientName":"redis-py","id":"Python","langId":"python","panelId":"panel_Python_search_vss-stepget_data"}]},{"codetabsId":"search_vss-stepdump_data","description":"Foundational: Inspect the structure of a single document from the demo dataset to understand the data format","difficulty":"beginner","id":"dump_data","languages":[{"clientId":"redis-py","clientName":"redis-py","id":"Python","langId":"python","panelId":"panel_Python_search_vss-stepdump_data"}]},{"codetabsId":"search_vss-stepload_data","description":"Practical pattern: Store demo data as JSON documents in Redis using JSON.SET with pipelining to minimize network round-trips","difficulty":"beginner","id":"load_data","languages":[{"clientId":"redis-py","clientName":"redis-py","id":"Python","langId":"python","panelId":"panel_Python_search_vss-stepload_data"}]},{"codetabsId":"search_vss-stepget","description":"Foundational: Retrieve a specific attribute from a JSON document in Redis using JSONPath expressions","difficulty":"beginner","id":"get","languages":[{"clientId":"redis-py","clientName":"redis-py","id":"Python","langId":"python","panelId":"panel_Python_search_vss-stepget"}]},{"codetabsId":"search_vss-stepget_keys","description":"Foundational: Retrieve all Redis keys with a specific prefix to identify documents for processing","difficulty":"beginner","id":"get_keys","languages":[{"clientId":"redis-py","clientName":"redis-py","id":"Python","langId":"python","panelId":"panel_Python_search_vss-stepget_keys"}]},{"codetabsId":"search_vss-stepgenerate_embeddings","description":"Create embeddings: Generate text embeddings from document descriptions using SentenceTransformers model to create vector representations","difficulty":"intermediate","id":"generate_embeddings","languages":[{"clientId":"redis-py","clientName":"redis-py","id":"Python","langId":"python","panelId":"panel_Python_search_vss-stepgenerate_embeddings"}]},{"codetabsId":"search_vss-stepload_embeddings","description":"Practical pattern: Insert generated vector embeddings into JSON documents using JSON.SET with pipelining for efficient batch updates","difficulty":"intermediate","id":"load_embeddings","languages":[{"clientId":"redis-py","clientName":"redis-py","id":"Python","langId":"python","panelId":"panel_Python_search_vss-stepload_embeddings"}]},{"codetabsId":"search_vss-stepdump_example","description":"Foundational: Inspect an updated document containing both original data and generated vector embeddings using JSON.GET","difficulty":"intermediate","id":"dump_example","languages":[{"clientId":"redis-py","clientName":"redis-py","id":"Python","langId":"python","panelId":"panel_Python_search_vss-stepdump_example"}]},{"codetabsId":"search_vss-stepcreate_index","description":"Foundational: Create an index on JSON documents with vector field using FT.CREATE with FLAT indexing and COSINE distance metric","difficulty":"intermediate","id":"create_index","languages":[{"id":"redis-cli","panelId":"panel_redis-cli_search_vss-stepcreate_index"},{"clientId":"redis-py","clientName":"redis-py","id":"Python","langId":"python","panelId":"panel_Python_search_vss-stepcreate_index"}]},{"codetabsId":"search_vss-stepvalidate_index","description":"Practical pattern: Check the state and statistics of an index using FT.INFO to verify successful indexing of documents","difficulty":"intermediate","id":"validate_index","languages":[{"id":"redis-cli","panelId":"panel_redis-cli_search_vss-stepvalidate_index"},{"clientId":"redis-py","clientName":"redis-py","id":"Python","langId":"python","panelId":"panel_Python_search_vss-stepvalidate_index"}]},{"codetabsId":"search_vss-stepdef_bulk_queries","description":"Foundational: Define a list of text queries to use for vector search operations","difficulty":"beginner","id":"def_bulk_queries","languages":[{"clientId":"redis-py","clientName":"redis-py","id":"Python","langId":"python","panelId":"panel_Python_search_vss-stepdef_bulk_queries"}]},{"codetabsId":"search_vss-stepenc_bulk_queries","description":"Create query embeddings: Encode text queries as vector embeddings using the same SentenceTransformers model used for document embeddings","difficulty":"intermediate","id":"enc_bulk_queries","languages":[{"clientId":"redis-py","clientName":"redis-py","id":"Python","langId":"python","panelId":"panel_Python_search_vss-stepenc_bulk_queries"}]},{"codetabsId":"search_vss-stepdefine_bulk_query","description":"Query data: Execute multiple vector search queries and format results into a Pandas table for visualization and analysis","difficulty":"advanced","id":"define_bulk_query","languages":[{"clientId":"redis-py","clientName":"redis-py","id":"Python","langId":"python","panelId":"panel_Python_search_vss-stepdefine_bulk_query"}]},{"codetabsId":"search_vss-steprun_knn_query","description":"Semantic search: Execute K-nearest neighbors vector search using FT.SEARCH with KNN algorithm to find semantically similar documents","difficulty":"advanced","id":"run_knn_query","languages":[{"clientId":"redis-py","clientName":"redis-py","id":"Python","langId":"python","panelId":"panel_Python_search_vss-steprun_knn_query"}]}]
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


This quick start guide helps you to:

1. Understand what a vector database is
2. Create a Redis vector database
3. Create vector embeddings and store vectors
4. Query data and perform a vector search

This guide uses [RedisVL](https://redis.io/docs/latest/develop/clients/redis-vl),
which is a Python client library for Redis that is highly specialized for
vector processing. You may also be interested in the vector query examples
for our other client libraries:

- [`redis-py` (Python)](https://redis.io/docs/latest/develop/clients/redis-py/vecsearch)
- [`NRedisStack`(C#/.NET)](https://redis.io/docs/latest/develop/clients/dotnet/nredisstack/vecsearch)
- [`node-redis` (JavaScript/Node.js)](https://redis.io/docs/latest/develop/clients/nodejs/vecsearch)
- [`jedis` (Java)](https://redis.io/docs/latest/develop/clients/jedis/vecsearch)
- [`go-redis` (Go)](https://redis.io/docs/latest/develop/clients/go/vecsearch)


## Understand vector databases

Data is often unstructured, which means that it isn't described by a well-defined schema. Examples of unstructured data include text passages, images, videos, or audio. One approach to storing and searching through unstructured data is to use vector embeddings.

**What are vectors?** In machine learning and AI, vectors are sequences of numbers that represent data. They are the inputs and outputs of models, encapsulating underlying information in a numerical form. Vectors transform unstructured data, such as text, images, videos, and audio, into a format that machine learning models can process.

- **Why are they important?** Vectors capture complex patterns and semantic meanings inherent in data, making them powerful tools for a variety of applications. They allow machine learning models to understand and manipulate unstructured data more effectively.
- **Enhancing traditional search.** Traditional keyword or lexical search relies on exact matches of words or phrases, which can be limiting. In contrast, vector search, or semantic search, leverages the rich information captured in vector embeddings. By mapping data into a vector space, similar items are positioned near each other based on their meaning. This approach allows for more accurate and meaningful search results, as it considers the context and semantic content of the query rather than just the exact words used.


## Create a Redis vector database
You can use [Redis Open Source](https://redis.io/docs/latest/operate/oss_and_stack/) as a vector database. It allows you to:

* Store vectors and the associated metadata within hashes or [JSON](https://redis.io/docs/latest/develop/data-types/json) documents
* Create and configure secondary indices for search
* Perform vector searches
* Update vectors and metadata
* Delete and cleanup

The easiest way to get started is to use Redis Cloud:

1. Create a [free account](https://redis.com/try-free?utm_source=redisio&utm_medium=referral&utm_campaign=2023-09-try_free&utm_content=cu-redis_cloud_users).

   <img src="../img/free-cloud-db.png" width="500px">
2. Follow the instructions to create a free database.

This free Redis Cloud database comes out of the box with all the Redis Open Source features.

You can alternatively use the [installation guides](https://redis.io/docs/latest/operate/oss_and_stack/install/install-stack/) to install Redis on your local machine.

## Install the required Python packages

Create a Python virtual environment and install the following dependencies using `pip`:

* `redis`: You can find further details about the `redis-py` client library in the [clients](https://redis.io/docs/latest/develop/clients/redis-py) section of this documentation site.
* `pandas`: Pandas is a data analysis library.
* `sentence-transformers`: You will use the [SentenceTransformers](https://www.sbert.net/) framework to generate embeddings on full text.
* `tabulate`: `pandas` uses `tabulate` to render Markdown.

You will also need the following imports in your Python code:

Foundational: Import required Python packages for vector database operations including redis, pandas, and sentence-transformers

**Difficulty:** Beginner

**Available in:** Redis CLI, Python

##### Redis CLI

```
## Connect

Connect to Redis. By default, Redis returns binary responses. To decode them, you pass the `decode_responses` parameter set to `True`:

Foundational: Connect to a Redis server with decode_responses enabled to receive decoded strings instead of bytes

**Difficulty:** Beginner

**Available in:** Python

##### Python

```python
client = redis.Redis(host="localhost", port=6379, decode_responses=True)
```


<br/>

Instead of using a local Redis server, you can copy and paste the connection details from the Redis Cloud database configuration page. Here is an example connection string of a Cloud database that is hosted in the AWS region `us-east-1` and listens on port 16379: `redis-16379.c283.us-east-1-4.ec2.cloud.redislabs.com:16379`. The connection string has the format `host:port`. You must also copy and paste the username and password of your Cloud database. The line of code for connecting with the default user changes then to `client = redis.Redis(host="redis-16379.c283.us-east-1-4.ec2.cloud.redislabs.com", port=16379, password="your_password_here", decode_responses=True)`.



## Prepare the demo dataset

This quick start guide also uses the **bikes** dataset. Here is an example document from it:

```json
{
  "model": "Jigger",
  "brand": "Velorim",
  "price": 270,
  "type": "Kids bikes",
  "specs": {
    "material": "aluminium",
    "weight": "10"
  },
  "description": "Small and powerful, the Jigger is the best ride for the smallest of tikes! ..."
}
```

The `description` field contains free-form text descriptions of bikes and will be used to create vector embeddings.


###  1. Fetch the demo data
You need to first fetch the demo dataset as a JSON array:

Foundational: Fetch the demo dataset as a JSON array to prepare data for vector database operations

**Difficulty:** Beginner

**Available in:** Python

##### Python

```python
URL = ("https://raw.githubusercontent.com/bsbodden/redis_vss_getting_started"
       "/main/data/bikes.json"
       )
response = requests.get(URL, timeout=10)
bikes = response.json()
```



Inspect the structure of one of the bike JSON documents:

Foundational: Inspect the structure of a single document from the demo dataset to understand the data format

**Difficulty:** Beginner

**Available in:** Python

##### Python

```python
json.dumps(bikes[0], indent=2)
```



### 2. Store the demo data in Redis
Now iterate over the `bikes`  array to store the data as [JSON](https://redis.io/docs/latest/develop/data-types/json/) documents in Redis by using the [JSON.SET](https://redis.io/docs/latest/commands/json.set/) command. The below code uses a [pipeline](https://redis.io/docs/latest/develop/using-commands/pipelining) to minimize the network round-trip times:

Practical pattern: Store demo data as JSON documents in Redis using JSON.SET with pipelining to minimize network round-trips

**Difficulty:** Beginner

**Available in:** Python

##### Python

```python
pipeline = client.pipeline()
for i, bike in enumerate(bikes, start=1):
    redis_key = f"bikes:{i:03}"
    pipeline.json().set(redis_key, "$", bike)
res = pipeline.execute()
# >>> [True, True, True, True, True, True, True, True, True, True, True]
```



Once loaded, you can retrieve a specific attribute from one of the JSON documents in Redis using a [JSONPath](https://goessner.net/articles/JsonPath/) expression:

Foundational: Retrieve a specific attribute from a JSON document in Redis using JSONPath expressions

**Difficulty:** Beginner

**Available in:** Python

##### Python

```python
res = client.json().get("bikes:010", "$.model")
# >>> ['Summit']
```



### 3. Select a text embedding model

[HuggingFace](https://huggingface.co) has a large catalog of text embedding models that are locally servable through the `SentenceTransformers` framework. Here we use the [MS MARCO](https://microsoft.github.io/msmarco/) model that is widely used in search engines, chatbots, and other AI applications.

```python
from sentence_transformers import SentenceTransformer

embedder = SentenceTransformer('msmarco-distilbert-base-v4')
```

### 4. Generate text embeddings
Iterate over all the Redis keys with the prefix `bikes:`:

Foundational: Retrieve all Redis keys with a specific prefix to identify documents for processing

**Difficulty:** Beginner

**Available in:** Python

##### Python

```python
keys = sorted(client.keys("bikes:*"))
# >>> ['bikes:001', 'bikes:002', ..., 'bikes:011']
```



Use the keys as input to the [JSON.MGET](https://redis.io/docs/latest/commands/json.mget/) command, along with the `$.description` field, to collect the descriptions in a list. Then, pass the list of descriptions to the `.encode()` method:

Create embeddings: Generate text embeddings from document descriptions using SentenceTransformers model to create vector representations

**Difficulty:** Intermediate

**Available in:** Python

##### Python

```python
descriptions = client.json().mget(keys, "$.description")
descriptions = [item for sublist in descriptions for item in sublist]
embedder = SentenceTransformer("msmarco-distilbert-base-v4")
embeddings = embedder.encode(descriptions).astype(np.float32).tolist()
VECTOR_DIMENSION = len(embeddings[0])
# >>> 768
```



Insert the vectorized descriptions to the bike documents in Redis using the [JSON.SET](https://redis.io/docs/latest/commands/json.set) command. The following command inserts a new field into each of the documents under the JSONPath `$.description_embeddings`. Once again, do this using a pipeline to avoid unnecessary network round-trips:

Practical pattern: Insert generated vector embeddings into JSON documents using JSON.SET with pipelining for efficient batch updates

**Difficulty:** Intermediate

**Available in:** Python

##### Python

```python
pipeline = client.pipeline()
for key, embedding in zip(keys, embeddings):
    pipeline.json().set(key, "$.description_embeddings", embedding)
pipeline.execute()
# >>> [True, True, True, True, True, True, True, True, True, True, True]
```



Inspect one of the updated bike documents using the [JSON.GET](https://redis.io/docs/latest/commands/json.get) command:

Foundational: Inspect an updated document containing both original data and generated vector embeddings using JSON.GET

**Difficulty:** Intermediate

**Available in:** Python

##### Python

```python
res = client.json().get("bikes:010")
# >>>
# {
#   "model": "Summit",
#   "brand": "nHill",
#   "price": 1200,
#   "type": "Mountain Bike",
#   "specs": {
#     "material": "alloy",
#     "weight": "11.3"
#   },
#   "description": "This budget mountain bike from nHill performs well..."
#   "description_embeddings": [
#     -0.538114607334137,
#     -0.49465855956077576,
#     -0.025176964700222015,
#     ...
#   ]
# }
```




When storing a vector embedding within a JSON document, the embedding is stored as a JSON array. In the example above, the array was shortened considerably for the sake of readability.



## Create an index

### 1. Create an index with a vector field

You must create an index to query document metadata or to perform vector searches. Use the [FT.CREATE](https://redis.io/docs/latest/commands/ft.create) command:


FT.CREATE idx:bikes_vss ON JSON
  PREFIX 1 bikes: SCORE 1.0
  SCHEMA
    $.model AS model TEXT WEIGHT 1.0 NOSTEM
    $.brand AS brand TEXT WEIGHT 1.0 NOSTEM
    $.price AS price NUMERIC
    $.type TAG SEPARATOR ","
    $.description AS description TEXT WEIGHT 1.0
    $.description_embeddings AS vector VECTOR FLAT 6 TYPE FLOAT32 DIM 768 DISTANCE_METRIC COSINE
```

##### Python

```python
import json
import time

import numpy as np
import pandas as pd
import requests
import redis
from redis.commands.search.field import (
    NumericField,
    TagField,
    TextField,
    VectorField,
)
from redis.commands.search.index_definition import IndexDefinition, IndexType
from redis.commands.search.query import Query
from sentence_transformers import SentenceTransformer

```



Here is a breakdown of the `VECTOR` field definition:

* `$.description_embeddings AS vector`: The vector field's JSON path and its field alias `vector`.
* `FLAT`: Specifies the indexing method, which is either a flat index or a hierarchical navigable small world graph ([HNSW](https://arxiv.org/ftp/arxiv/papers/1603/1603.09320.pdf)).
* `TYPE FLOAT32`: Sets the float precision of a vector component, in this case a 32-bit floating point number.
* `DIM 768`: The length or dimension of the embeddings, determined by the chosen embedding model.
* `DISTANCE_METRIC COSINE`: The chosen distance function: [cosine distance](https://en.wikipedia.org/wiki/Cosine_similarity).

You can find further details about all these options in the [vector reference documentation](https://redis.io/docs/latest/develop/ai/search-and-query/vectors).

### 2. Check the state of the index

As soon as you execute the [FT.CREATE](https://redis.io/docs/latest/commands/ft.create) command, the indexing process runs in the background. In a short time, all JSON documents should be indexed and ready to be queried. To validate that, you can use the [FT.INFO](https://redis.io/docs/latest/commands/ft.info) command, which provides details and statistics about the index. Of particular interest are the number of documents successfully indexed and the number of failures:

Practical pattern: Check the state and statistics of an index using FT.INFO to verify successful indexing of documents

**Difficulty:** Intermediate

**Available in:** Redis CLI, Python

##### Redis CLI

```
FT.INFO idx:bikes_vss
```

##### Python

```python
info = client.ft("idx:bikes_vss").info()
num_docs = info["num_docs"]
indexing_failures = info["hash_indexing_failures"]
# print(f"{num_docs} documents indexed with {indexing_failures} failures")
# >>> 11 documents indexed with 0 failures
```



## Perform vector searches

This quick start guide focuses on vector search. However, you can learn more about how to query based on document metadata in the [document database quick start guide](https://redis.io/docs/latest/develop/get-started/document-database).

### 1. Embed your queries

The following code snippet shows a list of text queries you will use to perform vector search in Redis:

Foundational: Define a list of text queries to use for vector search operations

**Difficulty:** Beginner

**Available in:** Python

##### Python

```python
queries = [
    "Bike for small kids",
    "Best Mountain bikes for kids",
    "Cheap Mountain bike for kids",
    "Female specific mountain bike",
    "Road bike for beginners",
    "Commuter bike for people over 60",
    "Comfortable commuter bike",
    "Good bike for college students",
    "Mountain bike for beginners",
    "Vintage bike",
    "Comfortable city bike",
]
```



First, encode each input query as a vector embedding using the same SentenceTransformers model:

Create query embeddings: Encode text queries as vector embeddings using the same SentenceTransformers model used for document embeddings

**Difficulty:** Intermediate

**Available in:** Python

##### Python

```python
encoded_queries = embedder.encode(queries)
len(encoded_queries)
# >>> 11
```



<br/>

It is vital that you use the same embedding model to embed your queries as you did your documents. Using a different model will result in poor semantic search results or error.


### 2. K-nearest neighbors (KNN) search
The KNN algorithm calculates the distance between the query vector and each vector in Redis based on the chosen distance function. It then returns the top K items with the smallest distances to the query vector. These are the most semantically similar items.

Now construct a query to do just that:

```python
query = (
    Query('(*)=>[KNN 3 @vector $query_vector AS vector_score]')
     .sort_by('vector_score')
     .return_fields('vector_score', 'id', 'brand', 'model', 'description')
     .dialect(2)
)
```

Let's break down the above query template:
- The filter expression `(*)` means `all`. In other words, no filtering was applied. You could replace it with an expression that filters by additional metadata.
- The `KNN` part of the query searches for the top 3 nearest neighbors.
- The query vector must be passed in as the param `query_vector`.
- The distance to the query vector is returned as `vector_score`.
- The results are sorted by this `vector_score`.
- Finally, it returns the fields `vector_score`,  `id`, `brand`, `model`, and `description` for each result.


To utilize a vector query with the [`FT.SEARCH`](https://redis.io/docs/latest/commands/ft.search/) command, you must specify DIALECT 2 or greater.


You must pass the vectorized query as a byte array with the param name `query_vector`. The following code creates a Python NumPy array from the query vector and converts it into a compact, byte-level representation that can be passed as a parameter to the query:

```python
for i, encoded_query in enumerate(encoded_queries):
    result = client.ft('idx:bikes_vss').search(
        query,
        {
          'query_vector': np.array(encoded_query, dtype=np.float32).tobytes()
        }
    )
    print(f"Results for query '{queries[i]}':")
    for doc in result.docs:
        print(f"\t{doc.id}: {doc.brand} {doc.model}")
```

With the template for the query in place, you can execute all queries in a loop. Notice that the script calculates the `vector_score` for each result as `1 - doc.vector_score`. Because the cosine distance is used as the metric, the items with the smallest distance are closer and, therefore, more similar to the query.

Then, loop over the matched documents and create a list of results that can be converted into a Pandas table to visualize the results:

Query data: Execute multiple vector search queries and format results into a Pandas table for visualization and analysis

**Difficulty:** Advanced

**Available in:** Python

##### Python

```python
def create_query_table(query, queries, encoded_queries, extra_params=None):
    """
    Creates a query table.
    """
    results_list = []
    for i, encoded_query in enumerate(encoded_queries):
        result_docs = (
            client.ft("idx:bikes_vss")
            .search(
                query,
                {"query_vector": np.array(encoded_query, dtype=np.float32).tobytes()}
                | (extra_params if extra_params else {}),
            )
            .docs
        )
        for doc in result_docs:
            vector_score = round(1 - float(doc.vector_score), 2)
            results_list.append(
                {
                    "query": queries[i],
                    "score": vector_score,
                    "id": doc.id,
                    "brand": doc.brand,
                    "model": doc.model,
                    "description": doc.description,
                }
            )

    # Optional: convert the table to Markdown using Pandas
    queries_table = pd.DataFrame(results_list)
    queries_table.sort_values(
        by=["query", "score"], ascending=[True, False], inplace=True
    )
    queries_table["query"] = queries_table.groupby("query")["query"].transform(
        lambda x: [x.iloc[0]] + [""] * (len(x) - 1)
    )
    queries_table["description"] = queries_table["description"].apply(
        lambda x: (x[:497] + "...") if len(x) > 500 else x
    )
    return queries_table.to_markdown(index=False)


```



The query results show the individual queries' top three matches (our K parameter) along with the bike's id, brand, and model for each query.

For example, for the query "Best Mountain bikes for kids", the highest similarity score (`0.54`) and, therefore the closest match was the 'Nord' brand 'Chook air 5' bike model, described as:

> The Chook Air 5 gives kids aged six years and older a durable and uberlight mountain bike for their first experience on tracks and easy cruising through forests and fields. The lower top tube makes it easy to mount and dismount in any situation, giving your kids greater safety on the trails. The Chook Air 5 is the perfect intro to mountain biking.

From the description, this bike is an excellent match for younger children, and the embeddings accurately captured the semantics of the description.

Semantic search: Execute K-nearest neighbors vector search using FT.SEARCH with KNN algorithm to find semantically similar documents

**Difficulty:** Advanced

**Available in:** Python

##### Python

```python
query = (
    Query("(*)=>[KNN 3 @vector $query_vector AS vector_score]")
    .sort_by("vector_score")
    .return_fields("vector_score", "id", "brand", "model", "description")
    .dialect(2)
)

table = create_query_table(query, queries, encoded_queries)
print(table)
# >>> | Best Mountain bikes for kids     |    0.54 | bikes:003...
```



| query | score | id | brand | model | description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Best Mountain bikes for kids | 0.54 | bikes:003 | Nord | Chook air 5 | The Chook Air 5  gives kids aged six years and older a durable and uberlight mountain bike for their first experience on tracks and easy cruising through forests and fields. The lower  top tube makes it easy to mount and dismount in any situation, giving your kids greater safety on the trails. The Chook Air 5 is the perfect intro to mountain biking. |
|  | 0.51 | bikes:010 | nHill | Summit | This budget mountain bike from nHill performs well both on bike paths and on the trail. The fork with 100mm of travel absorbs rough terrain. Fat Kenda Booster tires give you grip in corners and on wet trails. The Shimano Tourney drivetrain offered enough gears for finding a comfortable pace to ride uphill, and the Tektro hydraulic disc brakes break smoothly. Whether you want an affordable bike that you can take to work, but also take trail riding on the weekends or you’re just after a stable,... |
|  | 0.46 | bikes:001 | Velorim | Jigger | Small and powerful, the Jigger is the best ride for the smallest of tikes! This is the tiniest kids’ pedal bike on the market available without a coaster brake, the Jigger is the vehicle of choice for the rare tenacious little rider raring to go. We say rare because this smokin’ little bike is not ideal for a nervous first-time rider, but it’s a true giddy up for a true speedster. The Jigger is a 12 inch lightweight kids bicycle and it will meet your little one’s need for speed. It’s a single... |


## Next steps

1. You can learn more about the query options, such as filters and vector range queries, by reading the [vector reference documentation](https://redis.io/docs/latest/develop/ai/search-and-query/vectors).
2. The complete [Redis Search documentation](https://redis.io/docs/latest/develop/ai/search-and-query/) might be interesting for you.
3. If you want to follow the code examples more interactively, then you can use the [Jupyter notebook](https://github.com/redis-developer/redis-ai-resources/blob/main/python-recipes/vector-search/00_redispy.ipynb) that inspired this quick start guide.
4. If you want to see more advanced examples of a Redis vector database in action, visit the [Redis AI Resources](https://github.com/redis-developer/redis-ai-resources) page on GitHub.

## Continue learning with Redis University



