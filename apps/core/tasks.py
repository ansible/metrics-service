"""
Background tasks for metrics_service using dispatcherd.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def cleanup_old_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clean up old data from the system.

    Args:
        data: Task data containing cleanup parameters

    Returns:
        Task result dictionary
    """
    logger.info("Starting cleanup of old data")

    # Example cleanup logic - replace with actual cleanup code
    days_old = data.get("days_old", 30)

    # Simulate cleanup work
    cleaned_count = 0

    try:
        # Add your actual cleanup logic here
        # For example: delete old activity stream entries, logs, etc.
        logger.info(f"Cleaning up data older than {days_old} days")

        # Example: Clean up old activity stream data
        # ActivityStream.objects.filter(
        #     timestamp__lt=timezone.now() - timedelta(days=days_old)
        # ).delete()

        logger.info(f"Cleanup completed. Cleaned {cleaned_count} items")

        return {
            "status": "success",
            "cleaned_count": cleaned_count,
            "days_old": days_old,
        }

    except Exception as e:
        logger.error(f"Cleanup failed: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
        }


def send_notification_email(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send notification email to users.

    Args:
        data: Task data containing email parameters

    Returns:
        Task result dictionary
    """
    logger.info("Sending notification email")

    recipient = data.get("recipient")
    subject = data.get("subject", "Notification")

    try:
        # Add your actual email sending logic here
        # For example: using Django's send_mail
        # send_mail(
        #     subject=subject,
        #     message=data.get("message", ""),
        #     from_email=settings.DEFAULT_FROM_EMAIL,
        #     recipient_list=[recipient],
        # )

        logger.info(f"Email sent to {recipient} with subject: {subject}")

        return {
            "status": "success",
            "recipient": recipient,
            "subject": subject,
        }

    except Exception as e:
        logger.error(f"Email sending failed: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
        }


def process_user_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process user data in the background.

    Args:
        data: Task data containing user processing parameters

    Returns:
        Task result dictionary
    """
    logger.info("Processing user data")

    user_id = data.get("user_id")
    operation = data.get("operation", "sync")

    try:
        from .models import User

        user = User.objects.get(id=user_id)
        logger.info(f"Processing user: {user.username}")

        if operation == "sync":
            # Example: Sync user data with external systems
            logger.info(f"Syncing user {user.username} with external systems")

        elif operation == "validate":
            # Example: Validate user data
            logger.info(f"Validating user {user.username} data")

        logger.info(f"User processing completed for {user.username}")

        return {
            "status": "success",
            "user_id": user_id,
            "username": user.username,
            "operation": operation,
        }

    except Exception as e:
        logger.error(f"User processing failed: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
        }


# Task configuration for dispatcherd
TASK_FUNCTIONS = {
    "cleanup_old_data": cleanup_old_data,
    "send_notification_email": send_notification_email,
    "process_user_data": process_user_data,
}

# Scheduled tasks configuration
SCHEDULED_TASKS = {
    "daily_cleanup": {
        "function": "cleanup_old_data",
        "schedule": 86400,  # Run daily (in seconds)
        "data": {"days_old": 30},
    },
}
