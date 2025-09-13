#!/usr/bin/env python3
"""
Debug script to test Supabase upload functionality
Run this to isolate the upload issue
"""

import json
import tempfile
import os
from pathlib import Path

try:
    from clients.supabase_client import SupabaseClient
    import config
except ImportError as e:
    print(f"❌ Import error: {e}")
    exit(1)

def test_supabase_connection():
    """Test basic Supabase connection and environment variables"""
    print("🔍 TESTING SUPABASE CONNECTION")
    print("=" * 50)
    
    # Check environment variables
    print(f"SUPABASE_URL exists: {hasattr(config, 'SUPABASE_URL')}")
    print(f"SUPABASE_SERVICE_ROLE_KEY exists: {hasattr(config, 'SUPABASE_SERVICE_ROLE_KEY')}")
    
    if hasattr(config, 'SUPABASE_URL'):
        url = getattr(config, 'SUPABASE_URL', '')
        print(f"SUPABASE_URL preview: {url[:50]}..." if len(url) > 50 else f"SUPABASE_URL: {url}")
        
    if hasattr(config, 'SUPABASE_SERVICE_ROLE_KEY'):
        key = getattr(config, 'SUPABASE_SERVICE_ROLE_KEY', '')
        print(f"SUPABASE_SERVICE_ROLE_KEY length: {len(key)}")
    
    # Try to initialize client
    try:
        print("\n🔧 Initializing SupabaseClient...")
        client = SupabaseClient(bucket_name="vm-sites")
        print("✅ SupabaseClient initialized successfully")
        return client
    except Exception as e:
        print(f"❌ Failed to initialize SupabaseClient: {e}")
        import traceback
        print(traceback.format_exc())
        return None

def test_upload_and_url(client):
    """Test file upload and URL generation"""
    if not client:
        print("❌ No client available for upload test")
        return
        
    print("\n📤 TESTING FILE UPLOAD AND URL GENERATION")
    print("=" * 50)
    
    # Create test data
    test_data = {
        "test": True,
        "message": "This is a test upload",
        "timestamp": "2024-01-01T00:00:00Z"
    }
    
    # Create temporary file
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
            json.dump(test_data, temp_file, indent=2)
            temp_file_path = temp_file.name
        
        print(f"📁 Created temp file: {temp_file_path}")
        print(f"📏 File size: {Path(temp_file_path).stat().st_size} bytes")
        
        # Test upload
        upload_path = "public/debug/test_upload.json"
        print(f"\n⬆️  Uploading to: {upload_path}")
        
        upload_result = client.upload_file(
            local_path=temp_file_path,
            remote_path=upload_path
        )
        
        if upload_result:
            print("✅ Upload successful!")
            print(f"📊 Upload result: {upload_result}")
            
            # Test URL generation
            print(f"\n🔗 Generating public URL...")
            try:
                public_url = client.get_public_url(upload_path)
                print(f"✅ Public URL generated: {public_url}")
                
                # Validate URL
                if public_url and public_url.startswith(('http://', 'https://')):
                    print("✅ URL validation passed")
                else:
                    print(f"❌ URL validation failed: {public_url}")
                    
            except Exception as url_error:
                print(f"❌ URL generation failed: {url_error}")
                import traceback
                print(traceback.format_exc())
        else:
            print("❌ Upload failed!")
            
    except Exception as e:
        print(f"❌ Upload test failed: {e}")
        import traceback
        print(traceback.format_exc())
    finally:
        # Cleanup
        if 'temp_file_path' in locals():
            try:
                os.unlink(temp_file_path)
                print(f"🗑️  Cleaned up temp file: {temp_file_path}")
            except Exception:
                pass

def main():
    """Main debug function"""
    print("🐛 SUPABASE UPLOAD DEBUG SCRIPT")
    print("=" * 50)
    
    # Test connection
    client = test_supabase_connection()
    
    # Test upload and URL generation
    test_upload_and_url(client)
    
    print("\n✅ Debug script completed!")

if __name__ == "__main__":
    main()

