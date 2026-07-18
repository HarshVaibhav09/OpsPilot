import chromadb

client = chromadb.PersistentClient(path="./test_chroma")

collection = client.get_or_create_collection("test")

collection.add(
    ids=["1"],
    documents=["hello world"]
)

print(collection.count())