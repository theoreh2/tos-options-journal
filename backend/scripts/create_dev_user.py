"""Create a dev user for local testing."""

import sys
sys.path.insert(0, ".")

from database import get_db_context
from models.db import Profile, Billing, generate_salt, compute_data_key

DEV_USER_ID = "00000000-0000-0000-0000-000000000001"

def create_dev_user():
    with get_db_context() as db:
        # Check if exists
        existing = db.query(Profile).filter(Profile.id == DEV_USER_ID).first()
        if existing:
            print(f"Dev user already exists with data_key: {existing.data_key}")
            return existing.data_key

        # Create profile
        salt = generate_salt()
        data_key = compute_data_key(DEV_USER_ID, salt)

        profile = Profile(
            id=DEV_USER_ID,
            salt=salt,
            data_key=data_key,
        )
        db.add(profile)

        # Create billing record
        billing = Billing(
            user_id=DEV_USER_ID,
            subscription_status="active",
            subscription_tier="pro",
        )
        db.add(billing)

        db.commit()
        print(f"Created dev user:")
        print(f"  ID: {DEV_USER_ID}")
        print(f"  data_key: {data_key}")
        return data_key


if __name__ == "__main__":
    create_dev_user()
