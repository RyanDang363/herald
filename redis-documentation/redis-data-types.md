# Redis data types

```json metadata
{
  "title": "Redis data types",
  "description": "Overview of data types supported by Redis",
  "categories": ["docs","develop","stack","oss","rs","rc","oss","kubernetes","clients"],
  "tableOfContents": {"sections":[{"children":[{"id":"strings","title":"Strings"},{"id":"bitfields","title":"Bitfields"},{"id":"bitmaps","title":"Bitmaps"},{"id":"arrays","title":"Arrays"},{"id":"geospatial-indexes","title":"Geospatial indexes"},{"id":"hashes","title":"Hashes"},{"id":"json","title":"JSON"},{"id":"lists","title":"Lists"},{"id":"probabilistic-data-types","title":"Probabilistic data types"},{"id":"bloom-filter","title":"Bloom filter"},{"id":"count-min-sketch","title":"Count-min sketch"},{"id":"cuckoo-filter","title":"Cuckoo filter"},{"id":"hyperloglog","title":"HyperLogLog"},{"id":"t-digest","title":"t-digest"},{"id":"top-k","title":"Top-K"},{"id":"sets","title":"Sets"},{"id":"sorted-sets","title":"Sorted sets"},{"id":"streams","title":"Streams"},{"id":"time-series","title":"Time series"},{"id":"vector-sets","title":"Vector sets"}],"id":"data-types","title":"Data types"},{"id":"adding-extensions","title":"Adding extensions"}]}

,
  "codeExamples": []
}
```
Redis is a data structure server.
At its core, Redis provides a collection of native data types that help you solve a wide variety of problems, from [caching](https://redis.io/docs/latest/develop/data-types/strings) to
[queuing](https://redis.io/docs/latest/develop/data-types/lists) to
[event processing](https://redis.io/docs/latest/develop/data-types/streams).
Below is a short description of each data type, with links to broader overviews and command references.
Each overview includes a comprehensive tutorial with code samples.

## Data types

[Redis Open Source](https://redis.io/docs/latest/operate/oss_and_stack)
implements the following data types:

- [Strings](#strings)
    - [Bitmaps](#bitmaps)
    - [Bitfields](#bitfields)
- [Arrays](#arrays)
- [Geospatial indexes](#geospatial-indexes)
- [Hashes](#hashes)
- [JSON](#json)
- [Lists](#lists)
- [Probabilistic data types](#probabilistic-data-types)
- [Sets](#sets)
- [Sorted sets](#sorted-sets)
- [Streams](#streams)
- [Time series](#time-series)
- [Vector sets](#vector-sets)

See [Compare data types](https://redis.io/docs/latest/develop/data-types/compare-data-types)
for advice on which of the general-purpose data types is best for common tasks.

### Strings 

[Redis strings](https://redis.io/docs/latest/develop/data-types/strings) are the most basic Redis data type, representing a sequence of bytes.
For more information, see:

* [Overview of Redis strings](https://redis.io/docs/latest/develop/data-types/strings)
* [Redis string command reference](https://redis.io/docs/latest/commands/?group=string)

### Bitfields

[Redis bitfields](https://redis.io/docs/latest/develop/data-types/strings/bitfields) efficiently encode multiple counters in a string value.
Bitfields provide atomic get, set, and increment operations and support different overflow policies.
For more information, see:

* [Overview of Redis bitfields](https://redis.io/docs/latest/develop/data-types/strings/bitfields)
* The [`BITFIELD`](https://redis.io/docs/latest/commands/bitfield) command.

### Bitmaps

[Redis bitmaps](https://redis.io/docs/latest/develop/data-types/strings/bitmaps) let you perform bitwise operations on strings. 
For more information, see:

* [Overview of Redis bitmaps](https://redis.io/docs/latest/develop/data-types/strings/bitmaps)
* [Redis bitmap command reference](https://redis.io/docs/latest/commands/?group=bitmap)

### Arrays

[Redis arrays](https://redis.io/docs/latest/develop/data-types/arrays) are sparse, index-addressable sequences of strings.
For more information, see:

* [Overview of Redis arrays](https://redis.io/docs/latest/develop/data-types/arrays)
* [Redis array command reference](https://redis.io/docs/latest/commands/?group=array)

### Geospatial indexes

[Redis geospatial indexes](https://redis.io/docs/latest/develop/data-types/geospatial) are useful for finding locations within a given geographic radius or bounding box.
For more information, see:

* [Overview of Redis geospatial indexes](https://redis.io/docs/latest/develop/data-types/geospatial)
* [Redis geospatial indexes command reference](https://redis.io/docs/latest/commands/?group=geo)

### Hashes

[Redis hashes](https://redis.io/docs/latest/develop/data-types/hashes) are record types modeled as collections of field-value pairs.
As such, Redis hashes resemble [Python dictionaries](https://docs.python.org/3/tutorial/datastructures.html#dictionaries), [Java HashMaps](https://docs.oracle.com/javase/8/docs/api/java/util/HashMap.html), and [Ruby hashes](https://ruby-doc.org/core-3.1.2/Hash.html).
For more information, see:

* [Overview of Redis hashes](https://redis.io/docs/latest/develop/data-types/hashes)
* [Redis hashes command reference](https://redis.io/docs/latest/commands/?group=hash)

### JSON

[Redis JSON](https://redis.io/docs/latest/develop/data-types/json) provides
structured, hierarchical arrays and key-value objects that match
the popular [JSON](https://www.json.org/json-en.html) text file
format. You can import JSON text into Redis objects and access,
modify, and query individual data elements.
For more information, see:

- [Overview of Redis JSON](https://redis.io/docs/latest/develop/data-types/json)
- [JSON command reference](https://redis.io/docs/latest/commands?group=json)

### Lists

[Redis lists](https://redis.io/docs/latest/develop/data-types/lists) are lists of strings sorted by insertion order.
For more information, see:

* [Overview of Redis lists](https://redis.io/docs/latest/develop/data-types/lists)
* [Redis list command reference](https://redis.io/docs/latest/commands/?group=list)

### Probabilistic data types

These data types let you gather and calculate statistics in a way
that is approximate but highly efficient. The following types are
available:

- [Bloom filter](#bloom-filter)
- [Count-min sketch](#count-min-sketch)
- [Cuckoo filter](#cuckoo-filter)
- [HyperLogLog](#hyperloglog)
- [t-digest](#t-digest)
- [Top-K](#top-k)

### Bloom filter

[Redis Bloom filters](https://redis.io/docs/latest/develop/data-types/probabilistic/bloom-filter)
let you check for the presence or absence of an element in a set. For more
information, see:

- [Overview of Redis Bloom filters](https://redis.io/docs/latest/develop/data-types/probabilistic/bloom-filter)
- [Bloom filter command reference](https://redis.io/docs/latest/commands?group=bf)

### Count-min sketch

[Redis Count-min sketch](https://redis.io/docs/latest/develop/data-types/probabilistic/count-min-sketch)
estimate the frequency of a data point within a stream of values.
For more information, see:

- [Redis Count-min sketch overview](https://redis.io/docs/latest/develop/data-types/probabilistic/count-min-sketch)
- [Count-min sketch command reference](https://redis.io/docs/latest/commands?group=cms)

### Cuckoo filter

[Redis Cuckoo filters](https://redis.io/docs/latest/develop/data-types/probabilistic/cuckoo-filter)
let you check for the presence or absence of an element in a set. They are similar to
[Bloom filters](#bloom-filter) but with slightly different trade-offs between features
and performance. For more information, see:

- [Overview of Redis Cuckoo filters](https://redis.io/docs/latest/develop/data-types/probabilistic/cuckoo-filter)
- [Cuckoo filter command reference](https://redis.io/docs/latest/commands?group=cf)

### HyperLogLog

The [Redis HyperLogLog](https://redis.io/docs/latest/develop/data-types/probabilistic/hyperloglogs) data structures provide probabilistic estimates of the cardinality (i.e., number of elements) of large sets. For more information, see:

* [Overview of Redis HyperLogLog](https://redis.io/docs/latest/develop/data-types/probabilistic/hyperloglogs)
* [Redis HyperLogLog command reference](https://redis.io/docs/latest/commands/?group=hyperloglog)

### t-digest

[Redis t-digest](https://redis.io/docs/latest/develop/data-types/probabilistic/t-digest)
structures estimate percentiles from a stream of data values. For more
information, see:

- [Redis t-digest overview](https://redis.io/docs/latest/develop/data-types/probabilistic/t-digest)
- [t-digest command reference](https://redis.io/docs/latest/commands?group=tdigest)

### Top-K

[Redis Top-K](https://redis.io/docs/latest/develop/data-types/probabilistic/top-k)
structures estimate the ranking of a data point within a stream of values.
For more information, see:

- [Redis Top-K overview](https://redis.io/docs/latest/develop/data-types/probabilistic/top-k)
- [Top-K command reference](https://redis.io/docs/latest/commands?group=topk)

### Sets

[Redis sets](https://redis.io/docs/latest/develop/data-types/sets) are unordered collections of unique strings that act like the sets from your favorite programming language (for example, [Java HashSets](https://docs.oracle.com/javase/7/docs/api/java/util/HashSet.html), [Python sets](https://docs.python.org/3.10/library/stdtypes.html#set-types-set-frozenset), and so on).
With a Redis set, you can add, remove, and test for existence in O(1) time (in other words, regardless of the number of set elements).
For more information, see:

* [Overview of Redis sets](https://redis.io/docs/latest/develop/data-types/sets)
* [Redis set command reference](https://redis.io/docs/latest/commands/?group=set)

### Sorted sets

[Redis sorted sets](https://redis.io/docs/latest/develop/data-types/sorted-sets) are collections of unique strings that maintain order by each string's associated score.
For more information, see:

* [Overview of Redis sorted sets](https://redis.io/docs/latest/develop/data-types/sorted-sets)
* [Redis sorted set command reference](https://redis.io/docs/latest/commands/?group=sorted-set)

### Streams

A [Redis stream](https://redis.io/docs/latest/develop/data-types/streams) is a data structure that acts like an append-only log.
Streams help record events in the order they occur and then syndicate them for processing.
For more information, see:

* [Overview of Redis Streams](https://redis.io/docs/latest/develop/data-types/streams)
* [Redis Streams command reference](https://redis.io/docs/latest/commands/?group=stream)

### Time series

[Redis time series](https://redis.io/docs/latest/develop/data-types/timeseries)
structures let you store and query timestamped data points.
For more information, see:

- [Redis time series overview](https://redis.io/docs/latest/develop/data-types/timeseries)
- [Time series command reference](https://redis.io/docs/latest/commands?group=timeseries)

### Vector sets

[Redis vector sets](https://redis.io/docs/latest/develop/data-types/vector-sets) are a specialized data type designed for managing high-dimensional vector data, enabling fast and efficient vector similarity search within Redis. Vector sets are optimized for use cases involving machine learning, recommendation systems, and semantic search, where each vector represents a data point in multi-dimensional space. Vector sets supports the [HNSW](https://en.wikipedia.org/wiki/Hierarchical_navigable_small_world) (hierarchical navigable small world) algorithm, allowing you to store, index, and query vectors based on the cosine similarity metric. With vector sets, Redis provides native support for hybrid search, combining vector similarity with structured [filters](https://redis.io/docs/latest/develop/data-types/vector-sets/filtered-search).
For more information, see:

* [Overview of Redis vector sets](https://redis.io/docs/latest/develop/data-types/vector-sets)
* [Redis vector set command reference](https://redis.io/docs/latest/commands/?group=vector_set)

## Adding extensions

To extend the features provided by the included data types, use one of these options:

1. Write your own custom [server-side functions in Lua](https://redis.io/docs/latest/develop/programmability/).
1. Write your own Redis module using the [modules API](https://redis.io/docs/latest/develop/reference/modules/) or check out the [community-supported modules](https://redis.io/docs/latest/operate/oss_and_stack/stack-with-enterprise/).

