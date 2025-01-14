# QdrantSync

**QdrantSync** is a powerful and flexible CLI tool designed to seamlessly migrate collections and data points between [Qdrant](https://qdrant.tech/documentation/) instances. It ensures efficient and reliable synchronization while maintaining data integrity and minimizing downtime.

## Features

- **Data Migration**: Transfer collections and data points from a source Qdrant instance to a destination with ease.
- **Customizable Options**:
  - Specify API keys and timeouts for secure and efficient data transfer.
  - Add prefixes to collection names for organized migrations.
  - Control replication and write consistency factors for destination collections.
  - Use thresholds to balance between approximate and exact counts for large datasets.
- **Incremental Migration**: Supports marking and tracking migrated data to resume or refresh migrations without duplication.
- **Batch Processing**: Handles large-scale migrations with scroll-based pagination, customizable batch sizes, and optional delays to avoid server overload.
- **Progress Monitoring**: Includes real-time progress tracking with detailed output for a smooth migration experience.
- **Error Handling**: Ensures safe operations with options like proceeding only if collections exist in the destination.

## Use Cases

- Migrate Qdrant data during infrastructure upgrades or cloud migrations.
- Synchronize data between staging and production environments.
- Back up collections to alternative Qdrant clusters.

## Getting Started

### Requirements

- Python 3.7 or higher
- Access to Qdrant instances (source and destination)

### Installation

#### (A) From PyPI (once available)

```bash
pip install QdrantSync
qdrantsync --help
```

#### Local Development / Editable Install

If you’re testing or contributing before it’s published on PyPI:

1. Clone this repository:
   ```bash
   git clone https://github.com/your-username/qdrantsync.git
   cd qdrantsync
   ```
2. Install in editable mode:
   ```bash
   pip install -e .
   ```
3. Now you can run:
   ```bash
   qdrantsync --help
   ```

### Usage

The basic command to migrate data between two Qdrant instances is:

```bash
qdrantsync \
  --source-url <source_instance_url> \
  --destination-url <destination_instance_url> \
  --migration-id <unique_migration_id>
```

You can mix and match other options like `--collection-prefix`, `--batch-delay`, `--replication-factor`, etc. for tailored migrations. For more details on available flags, use `qdrantsync --help`.

## Contribute

Contributions are welcome! Feel free to fork the repository, open an issue, or submit a pull request.
