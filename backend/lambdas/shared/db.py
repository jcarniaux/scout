"""
DynamoDB helper class for Scout backend.
"""
import boto3
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class DynamoDBHelper:
    """Wrapper around boto3 DynamoDB resource for common operations."""

    def __init__(self, region: str = "us-east-1"):
        """Initialize DynamoDB resource."""
        self.dynamodb = boto3.resource("dynamodb", region_name=region)

    def get_table(self, table_name: str) -> Any:
        """Get a DynamoDB table resource."""
        return self.dynamodb.Table(table_name)

    def get_item(self, table_name: str, key: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get a single item from DynamoDB.

        Args:
            table_name: Name of the table
            key: Primary key dict (e.g., {"PK": "USER#123", "SK": "JOB#456"})

        Returns:
            Item dict or None if not found
        """
        try:
            table = self.get_table(table_name)
            response = table.get_item(Key=key)
            return response.get("Item")
        except Exception as e:
            logger.error(f"Error getting item from {table_name}: {e}")
            raise

    def put_item(
        self, table_name: str, item: Dict[str, Any], condition_expression: Optional[str] = None
    ) -> bool:
        """
        Put an item into DynamoDB.

        Args:
            table_name: Name of the table
            item: Item dict to write
            condition_expression: Optional conditional expression (e.g., "attribute_not_exists(PK)")

        Returns:
            True if successful
        """
        try:
            table = self.get_table(table_name)
            kwargs = {"Item": item}
            if condition_expression:
                kwargs["ConditionExpression"] = condition_expression
            table.put_item(**kwargs)
            return True
        except self.dynamodb.meta.client.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.debug(f"Conditional check failed for {table_name} (expected for dedup)")
            else:
                logger.error(f"Error putting item to {table_name}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error putting item to {table_name}: {e}")
            raise

    def update_item(
        self,
        table_name: str,
        key: Dict[str, Any],
        update_expression: str,
        expression_attribute_values: Dict[str, Any],
        condition_expression: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update an item in DynamoDB.

        Args:
            table_name: Name of the table
            key: Primary key dict
            update_expression: DynamoDB UpdateExpression (e.g., "SET #status = :status")
            expression_attribute_values: Values for placeholders (e.g., {":status": "APPLIED"})
            condition_expression: Optional conditional expression

        Returns:
            Updated item dict
        """
        try:
            table = self.get_table(table_name)
            kwargs = {
                "Key": key,
                "UpdateExpression": update_expression,
                "ExpressionAttributeValues": expression_attribute_values,
                "ReturnValues": "ALL_NEW",
            }
            if condition_expression:
                kwargs["ConditionExpression"] = condition_expression
            response = table.update_item(**kwargs)
            return response.get("Attributes", {})
        except Exception as e:
            logger.error(f"Error updating item in {table_name}: {e}")
            raise

    def query(
        self,
        table_name: str,
        key_condition_expression: str,
        expression_attribute_values: Dict[str, Any],
        expression_attribute_names: Optional[Dict[str, str]] = None,
        index_name: Optional[str] = None,
        limit: Optional[int] = None,
        exclusive_start_key: Optional[Dict[str, Any]] = None,
        scan_index_forward: bool = True,
    ) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Query DynamoDB with pagination support.

        Args:
            table_name: Name of the table
            key_condition_expression: Key condition (e.g., "PK = :pk AND begins_with(SK, :sk)")
            expression_attribute_values: Values for placeholders
            expression_attribute_names: Optional attribute name mappings
            index_name: Optional GSI or LSI name
            limit: Optional result limit
            exclusive_start_key: Optional pagination token
            scan_index_forward: Sort order (True = ascending, False = descending)

        Returns:
            Tuple of (items list, last_evaluated_key or None)
        """
        try:
            table = self.get_table(table_name)
            kwargs = {
                "KeyConditionExpression": key_condition_expression,
                "ExpressionAttributeValues": expression_attribute_values,
                "ScanIndexForward": scan_index_forward,
            }
            if expression_attribute_names:
                kwargs["ExpressionAttributeNames"] = expression_attribute_names
            if index_name:
                kwargs["IndexName"] = index_name
            if limit:
                kwargs["Limit"] = limit
            if exclusive_start_key:
                kwargs["ExclusiveStartKey"] = exclusive_start_key

            response = table.query(**kwargs)
            return response.get("Items", []), response.get("LastEvaluatedKey")
        except Exception as e:
            logger.error(f"Error querying {table_name}: {e}")
            raise

    def scan(
        self,
        table_name: str,
        filter_expression: Optional[str] = None,
        expression_attribute_values: Optional[Dict[str, Any]] = None,
        expression_attribute_names: Optional[Dict[str, str]] = None,
        limit: Optional[int] = None,
        exclusive_start_key: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Scan DynamoDB table with optional filtering and pagination.

        Args:
            table_name: Name of the table
            filter_expression: Optional filter expression
            expression_attribute_values: Values for filter placeholders
            expression_attribute_names: Optional attribute name mappings
            limit: Optional result limit
            exclusive_start_key: Optional pagination token

        Returns:
            Tuple of (items list, last_evaluated_key or None)
        """
        try:
            table = self.get_table(table_name)
            kwargs = {}
            if filter_expression:
                kwargs["FilterExpression"] = filter_expression
            if expression_attribute_values:
                kwargs["ExpressionAttributeValues"] = expression_attribute_values
            if expression_attribute_names:
                kwargs["ExpressionAttributeNames"] = expression_attribute_names
            if limit:
                kwargs["Limit"] = limit
            if exclusive_start_key:
                kwargs["ExclusiveStartKey"] = exclusive_start_key

            response = table.scan(**kwargs)
            return response.get("Items", []), response.get("LastEvaluatedKey")
        except Exception as e:
            logger.error(f"Error scanning {table_name}: {e}")
            raise

    def batch_write(
        self, table_name: str, items_to_put: List[Dict[str, Any]], items_to_delete: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """
        Batch write items to DynamoDB.

        Args:
            table_name: Name of the table
            items_to_put: List of items to write
            items_to_delete: Optional list of keys to delete
        """
        try:
            table = self.get_table(table_name)
            with table.batch_writer() as batch:
                for item in items_to_put:
                    batch.put_item(Item=item)
                if items_to_delete:
                    for key in items_to_delete:
                        batch.delete_item(Key=key)
        except Exception as e:
            logger.error(f"Error batch writing to {table_name}: {e}")
            raise

    def delete_item(self, table_name: str, key: Dict[str, Any]) -> bool:
        """
        Delete an item from DynamoDB.

        Args:
            table_name: Name of the table
            key: Primary key dict

        Returns:
            True if successful
        """
        try:
            table = self.get_table(table_name)
            table.delete_item(Key=key)
            return True
        except Exception as e:
            logger.error(f"Error deleting item from {table_name}: {e}")
            raise
