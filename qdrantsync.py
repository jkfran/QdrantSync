#!/usr/bin/env python3
import time

import click
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue, PointStruct
from tqdm import tqdm


def get_total_points(
    source_client: QdrantClient,
    collection_name: str,
    migration_tag: str,
    exact_count_threshold: int,
    use_exact: bool = False
) -> int:
    """
    Get the total points needing migration, with fallback to exact count if needed.
    """
    count_result = source_client.count(
        collection_name=collection_name,
        count_filter=Filter(
            must_not=[FieldCondition(key=migration_tag, match=MatchValue(value=True))]
        ),
        exact=use_exact,
    )
    total_points = count_result.count

    # If approximate count is below threshold, re-run with exact=True
    if not use_exact and total_points < exact_count_threshold:
        click.echo(
            f"Approximate count ({total_points}) below threshold ({exact_count_threshold}), "
            f"re-running with exact=True."
        )
        total_points = get_total_points(
            source_client,
            collection_name,
            migration_tag,
            exact_count_threshold,
            use_exact=True,
        )

    return total_points


@click.command()
@click.option(
    "--source-url",
    required=True,
    help="URL of the source Qdrant instance.",
)
@click.option(
    "--source-api-key",
    default=None,
    help="API key for the source Qdrant instance. If not provided, no auth is used.",
)
@click.option(
    "--source-timeout",
    default=120,
    show_default=True,
    help="Timeout (in seconds) for the source Qdrant client.",
)
@click.option(
    "--destination-url",
    required=True,
    help="URL of the destination Qdrant instance (required).",
)
@click.option(
    "--destination-api-key",
    default=None,
    help="API key for the destination Qdrant instance. If not provided, no auth is used.",
)
@click.option(
    "--destination-timeout",
    default=120,
    show_default=True,
    help="Timeout (in seconds) for the destination Qdrant client.",
)
@click.option(
    "--collection-prefix",
    default="",
    show_default=True,
    help="Optional prefix to add to each collection name at the destination. "
         "If unset, no prefix is added."
)
@click.option(
    "--replication-factor",
    default=None,
    type=int,
    help=(
        "Replication factor for newly created collections in the destination. "
        "If not provided, the source collection's replication factor is used."
    ),
)
@click.option(
    "--proceed-if-exists",
    is_flag=True,
    default=False,
    show_default=True,
    help=(
        "If set, proceed with migration if the collection already exists in the "
        "destination. Otherwise, an exception is raised."
    ),
)
@click.option(
    "--migration-id",
    required=True,
    help=(
        "A mandatory migration ID for marking documents. The final payload key used is "
        "`_qdrant_sync_migration_{MIGRATION_ID}`. Must be the same across multiple runs "
        "to continue or refresh an existing migration."
    ),
)
@click.option(
    "--scroll-limit",
    default=500,
    show_default=True,
    help="Number of points to scroll through per batch.",
)
@click.option(
    "--exact-count-threshold",
    default=100_000,
    show_default=True,
    help=(
        "Threshold below which the script will use exact count instead of approximate "
        "count."
    ),
)
@click.option(
    "--count-update-interval",
    default=300,
    show_default=True,
    help="Interval (in seconds) to periodically update the approximate total count.",
)
@click.option(
    "--batch-delay",
    default=0.1,
    show_default=True,
    help="Delay (in seconds) after each batch to avoid overloading the server.",
)
def migrate_qdrant(
    source_url,
    source_api_key,
    source_timeout,
    destination_url,
    destination_api_key,
    destination_timeout,
    collection_prefix,
    replication_factor,
    proceed_if_exists,
    migration_id,
    scroll_limit,
    exact_count_threshold,
    count_update_interval,
    batch_delay,
):
    """
    Migrate data between Qdrant instances
    """

    # Construct the final migration tag from the user-supplied migration_id
    migration_tag = f"_qdrant_sync_migration_{migration_id}"

    # Instantiate Qdrant clients for source and destination
    source_client = QdrantClient(url=source_url, api_key=source_api_key, timeout=source_timeout)
    destination_client = QdrantClient(
        url=destination_url, api_key=destination_api_key, timeout=destination_timeout
    )

    # Retrieve collections from the source
    source_collections = source_client.get_collections().collections
    if not source_collections:
        click.echo("No collections found in the source cluster.")
        return

    click.echo(f"Found {len(source_collections)} collections in the source.")

    for collection_info in source_collections:
        collection_name = collection_info.name
        destination_collection_name = f"{collection_prefix}{collection_name}"

        click.echo(f"\nProcessing collection: {collection_name}")

        # Check if the collection already exists in the destination
        if destination_client.collection_exists(destination_collection_name):
            if not proceed_if_exists:
                raise click.ClickException(
                    f"Collection '{destination_collection_name}' already exists in the destination.\n"
                    "Use --proceed-if-exists to override."
                )
            else:
                click.echo(
                    f"Collection '{destination_collection_name}' already exists. "
                    "Proceeding with upserts for new or modified points."
                )
        else:
            # Retrieve source collection schema and create it in the destination
            source_info = source_client.get_collection(collection_name)
            schema = source_info.config

            # Use the replication factor provided by the user if specified;
            # otherwise, use the source schema’s value.
            final_replication_factor = (
                replication_factor
                if replication_factor is not None
                else schema.params.replication_factor
            )

            destination_client.create_collection(
                collection_name=destination_collection_name,
                vectors_config=schema.params.vectors,
                replication_factor=final_replication_factor,
                write_consistency_factor=schema.params.write_consistency_factor,
                on_disk_payload=schema.params.on_disk_payload,
            )
            click.echo(f"Created new collection '{destination_collection_name}' in destination.")

        # Get initial (approximate) total points to be migrated
        total_points = get_total_points(
            source_client=source_client,
            collection_name=collection_name,
            migration_tag=migration_tag,
            exact_count_threshold=exact_count_threshold,
            use_exact=False,
        )

        click.echo(f"Starting with an approximate total of {total_points} points to migrate.")

        # Initialize a progress bar
        with tqdm(total=total_points, desc=f"Migrating {collection_name}", unit="points") as pbar:
            next_page_offset = None
            last_count_update = time.time()

            while True:
                # Scroll through points that have not been migrated
                scroll_result = source_client.scroll(
                    collection_name=collection_name,
                    scroll_filter=Filter(
                        must_not=[FieldCondition(key=migration_tag, match=MatchValue(value=True))]
                    ),
                    limit=scroll_limit,
                    with_payload=True,
                    with_vectors=True,
                    offset=next_page_offset,
                )
                points, next_page_offset = scroll_result

                if not points:
                    break

                # If the current batch goes beyond the known total, adjust the total
                if pbar.n + len(points) > pbar.total:
                    pbar.total += len(points)

                # Prepare points for upsert
                formatted_points = []
                for point in points:
                    filtered_payload = {
                        k: v for k, v in point.payload.items() if k != migration_tag
                    }
                    formatted_points.append(
                        PointStruct(
                            id=point.id,
                            vector=point.vector,
                            payload=filtered_payload,
                        )
                    )

                # Upsert into the destination
                destination_client.upsert(
                    collection_name=destination_collection_name,
                    points=formatted_points,
                )

                # Mark points as migrated in the source
                point_ids = [point.id for point in points]
                source_client.set_payload(
                    collection_name=collection_name,
                    payload={migration_tag: True},
                    points=point_ids,
                )

                # Update progress bar
                pbar.update(len(points))

                # Periodically update the total point count
                if (time.time() - last_count_update) > count_update_interval:
                    new_count = get_total_points(
                        source_client=source_client,
                        collection_name=collection_name,
                        migration_tag=migration_tag,
                        exact_count_threshold=exact_count_threshold,
                        use_exact=False,
                    )
                    pbar.total = pbar.n + new_count
                    pbar.refresh()
                    last_count_update = time.time()

                # Check if there's more data to scroll
                if next_page_offset is None:
                    break

                # Optional delay to avoid overloading the server
                if batch_delay > 0:
                    time.sleep(batch_delay)

        click.echo(f"Collection '{collection_name}' migration completed.")

    click.echo("\nData migration for all collections completed successfully.")


if __name__ == "__main__":
    migrate_qdrant()
