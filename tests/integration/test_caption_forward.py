#!/usr/bin/env python3
"""
Integration test to verify 4 messages are forwarded with caption preserved.
Tests SenderAccount._forward_grouped_or_single method with real Telegram API.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.config import get_settings
from core.clients import load_clients
from tg.supabasefs import SupabaseTableFileSystem
import supabase
from messaging.telegram_sender import SenderAccount
from tg.utils import parse_telegram_message_url


async def test_caption_forward():
    """Test that forwards exactly 4 messages with caption"""

    print("🧪 INTEGRATION TEST: Caption Forward (4 messages)")
    print("=" * 60)

    try:
        # Load configuration
        settings = get_settings()
        clients_list = load_clients()
        client = clients_list[0]
        settings_list = client.load_settings()
        active_settings = [s for s in settings_list if s.active]
        account_name = list(set(setting.account for setting in active_settings))[0]

        print("📱 Account identified:")
        print(f"   Phone: {account_name}")
        print(f"   API ID: {settings.api_id}")

        # Set environment variables for tg package
        os.environ["API_ID"] = str(settings.api_id)
        os.environ["API_HASH"] = settings.api_hash

        # Create filesystem and account
        fs = SupabaseTableFileSystem(
            supabase.create_client(settings.supabase_url, settings.supabase_key),
            "sessions",
        )

        print("🔧 Creating SenderAccount...")
        account = SenderAccount(fs, account_name)
        print("✅ SenderAccount created")

        print("🔌 Starting account...")
        await account.start(revalidate=False)
        print("✅ Account started: PRO.ГАБ. (ID: 8426008235)")

        # Parse the message URL
        from_chat_id, message_id = parse_telegram_message_url(
            "https://t.me/pro_gab_sender_alerts/4625"
        )
        print(f"📨 Message to forward: {from_chat_id}/{message_id}")

        # Get source message info
        source_message = await account.app.get_messages(from_chat_id, ids=message_id)
        print(
            f"📊 Source message grouped_id: {getattr(source_message, 'grouped_id', None)}"
        )
        print(f"📝 Source message has text: {bool(source_message.text)}")
        print(f"📷 Source message has media: {bool(source_message.media)}")

        # Use the SenderAccount._forward_grouped_or_single method
        print("🎯 Using SenderAccount._forward_grouped_or_single...")

        result = await account._forward_grouped_or_single(
            chat_id="@leshchenko1979",  # Target user
            from_chat_id=from_chat_id,
            message_id=message_id,
        )

        print("✅ Forward completed!")
        print(f"📊 Result type: {type(result)}")

        if hasattr(result, "updates"):
            forwarded_count = len([u for u in result.updates if hasattr(u, "message")])
            print(f"💬 {forwarded_count} messages forwarded")

            # Analyze forwarded messages
            forwarded_messages = [
                u.message for u in result.updates if hasattr(u, "message") and u.message
            ]
            print(f"📋 Analyzing {len(forwarded_messages)} forwarded messages:")

            text_messages = 0
            media_messages = 0

            for i, msg in enumerate(forwarded_messages):
                has_text = bool(msg.message)
                has_media = bool(msg.media)

                if has_text:
                    text_messages += 1
                    text_preview = msg.message[:60] if msg.message else ""
                    print(f'   📝 Message {i + 1}: TEXT - "{text_preview}..."')
                elif has_media:
                    media_messages += 1
                    print(f"   📷 Message {i + 1}: MEDIA (photo/video)")
                else:
                    print(f"   ❓ Message {i + 1}: UNKNOWN")

            print(f"📊 Summary: {text_messages} text, {media_messages} media messages")

            # Check if we have 4 messages total with caption
            if forwarded_count == 4 and text_messages >= 1:
                print("✅ SUCCESS: 4 messages forwarded with caption preserved!")
                return True
            else:
                print(
                    f"❌ ISSUE: Expected 4 messages with caption, got {forwarded_count} total, {text_messages} with text"
                )
                return False

        await account.stop()
        print("✅ Account stopped")
        return False

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Run the integration test
    success = asyncio.run(test_caption_forward())
    if success:
        print("\n🎉 INTEGRATION TEST PASSED!")
        sys.exit(0)
    else:
        print("\n💥 INTEGRATION TEST FAILED!")
        sys.exit(1)
