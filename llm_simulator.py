#!/usr/bin/env python3
"""
LLM Output Speed Simulator
Simulates LLM text generation at 15 tokens per second
"""

import time
import sys
import random

# Sample text that simulates typical LLM responses
SAMPLE_RESPONSES = [
    "The concept of artificial intelligence has evolved significantly over the past decades, transforming from science fiction into practical applications that we encounter daily. Machine learning algorithms now power everything from recommendation systems to autonomous vehicles, fundamentally changing how we interact with technology.",
    
    "In software development, the choice of programming language often depends on the specific requirements of your project. Python excels in data science and rapid prototyping, while JavaScript dominates web development. Understanding these trade-offs helps developers make informed decisions about their technology stack.",
    
    "Climate change represents one of the most pressing challenges of our time, requiring coordinated global action across multiple sectors. Renewable energy technologies like solar and wind power have become increasingly cost-effective, making the transition to sustainable energy systems both environmentally necessary and economically viable.",
    
    "The history of computing began with mechanical calculators and evolved through vacuum tubes, transistors, and integrated circuits to today's powerful microprocessors. Each technological leap increased processing power while reducing size and cost, enabling the digital revolution that defines modern society.",
    
    "Effective communication in the workplace involves both verbal and non-verbal elements, requiring active listening, clear articulation of ideas, and emotional intelligence. Building strong professional relationships depends on understanding different communication styles and adapting your approach to work effectively with diverse teams."
]

def tokenize_text(text):
    """Realistic sub-word tokenization like real LLMs (BPE-style)"""
    import re
    tokens = []
    
    # Split text into words and spaces/punctuation
    parts = re.findall(r'\w+|\s+|[^\w\s]', text)
    
    for part in parts:
        if part.isspace():
            # Spaces are their own tokens
            tokens.append(part)
        elif part in ['.', ',', '!', '?', ';', ':']:
            # Punctuation are single tokens
            tokens.append(part)
        elif len(part) <= 3:
            # Short words are single tokens
            tokens.append(part)
        else:
            # Break longer words into sub-word tokens
            # Simulate BPE (Byte Pair Encoding) style tokenization
            if len(part) <= 6:
                # Medium words: split roughly in half
                mid = len(part) // 2
                tokens.extend([part[:mid], part[mid:]])
            else:
                # Long words: split into 2-4 character chunks
                i = 0
                while i < len(part):
                    chunk_size = min(3 + (i % 2), len(part) - i)  # Vary chunk size 3-4
                    tokens.append(part[i:i+chunk_size])
                    i += chunk_size
    
    return tokens

def simulate_llm_output(tokens_per_second=15):
    """Simulate LLM output at specified tokens per second"""
    delay_per_token = 1.0 / tokens_per_second
    
    print("🤖 LLM Output Simulator (15 tokens/second)")
    print("=" * 50)
    print("Press Ctrl+C to stop\n")
    
    try:
        while True:
            # Pick a random response
            response_text = random.choice(SAMPLE_RESPONSES)
            tokens = tokenize_text(response_text)
            
            print("🔄 Starting new response...\n")
            
            # Output tokens one by one with timing (no carriage return redraw)
            for token in tokens:
                # Write token directly, letting terminal handle wrapping
                sys.stdout.write(token)
                sys.stdout.flush()
                time.sleep(delay_per_token)
            
            print("\n\n" + "─" * 50 + "\n")
            time.sleep(2)  # Pause between responses
            
    except KeyboardInterrupt:
        print("\n\n✅ Simulation stopped!")

def main():
    print("Token speed options:")
    print("1. 15 tokens/second (default)")
    print("2. 10 tokens/second (slower)")
    print("3. 25 tokens/second (faster)")
    print("4. Custom speed")
    
    choice = input("\nSelect speed (1-4): ").strip()
    
    if choice == "2":
        speed = 10
    elif choice == "3":
        speed = 25
    elif choice == "4":
        try:
            speed = float(input("Enter tokens per second: "))
        except ValueError:
            print("Invalid input, using default 15 tokens/second")
            speed = 15
    else:
        speed = 15
    
    print(f"\n🚀 Starting simulation at {speed} tokens per second...")
    time.sleep(1)
    
    simulate_llm_output(speed)

if __name__ == "__main__":
    main()
