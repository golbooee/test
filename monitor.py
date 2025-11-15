import requests
import time
from datetime import datetime
import json
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

WALLET = "43jqgNCGAZQYwnk4s7Lt7P93S2sDkdN5bLKgUsGqVMoD6Bftsc5VVcHNy3mRBr7aBg5KgtFDHfYqK1MF8HEgSGucLbCCPeS"
CHECK_INTERVAL = 300

def clear_screen():
    print("\033[H\033[J", end="")

def get_supportxmr_stats_with_retry(max_retries=3):
    """Get SupportXMR stats with retry mechanism"""
    for attempt in range(max_retries):
        try:
            logger.info(f"Fetching SupportXMR stats (attempt {attempt + 1}/{max_retries})")
            # Get overall stats
            url = f"https://supportxmr.com/api/miner/{WALLET}/stats"
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            if response.status_code == 200:
                data = response.json()

                # Get worker names
                workers_list = []
                workers_count = 0
                total_worker_hashrate = 0
                try:
                    # Get worker identifiers (names only)
                    workers_url = f"https://supportxmr.com/api/miner/{WALLET}/identifiers"
                    workers_response = requests.get(workers_url, timeout=10)
                    workers_response.raise_for_status()

                    if workers_response.status_code == 200:
                        workers_data = workers_response.json()
                        if isinstance(workers_data, list):
                            workers_count = len(workers_data)
                            logger.info(f"Found {workers_count} workers")

                            # Get hashrate data from chart API
                            try:
                                chart_url = f"https://supportxmr.com/api/miner/{WALLET}/chart/hashrate/allWorkers"
                                chart_response = requests.get(chart_url, timeout=10)
                                chart_response.raise_for_status()

                                if chart_response.status_code == 200:
                                    chart_data = chart_response.json()

                                    # Process each worker
                                    for worker_name in workers_data:
                                        if isinstance(worker_name, str) and worker_name in chart_data:
                                            # Get latest hashrate from chart
                                            worker_chart = chart_data[worker_name]
                                            if worker_chart and len(worker_chart) > 0:
                                                latest_hash = worker_chart[0].get('hs', 0)
                                                total_worker_hashrate += latest_hash
                                                workers_list.append({
                                                    "id": worker_name,
                                                    "hashrate": latest_hash,
                                                    "last_share": worker_chart[0].get('ts', 0)
                                                })
                                            else:
                                                workers_list.append({
                                                    "id": worker_name,
                                                    "hashrate": 0,
                                                    "last_share": 0
                                                })
                                        elif isinstance(worker_name, str):
                                            workers_list.append({
                                                "id": worker_name,
                                                "hashrate": 0,
                                                "last_share": 0
                                            })
                            except Exception as e:
                                logger.warning(f"Failed to fetch worker chart data: {e}")
                except Exception as e:
                    logger.warning(f"Failed to fetch worker identifiers: {e}")

                # Calculate estimated hashrate from shares if worker API doesn't work
                total_hashes = data.get("totalHashes", 0)
                valid_shares = data.get("validShares", 0)

                # Use worker hashrate if available, otherwise use global hash
                final_hashrate = total_worker_hashrate if total_worker_hashrate > 0 else data.get("hash", 0) / 1000

                logger.info(f"Successfully fetched stats - Hashrate: {final_hashrate:.2f} H/s")
                return {
                    "pool": "SupportXMR",
                    "hashrate": final_hashrate,
                    "balance": data.get("amtDue", 0) / 1000000000000,
                    "paid": data.get("amtPaid", 0) / 1000000000000,
                    "workers": workers_count,
                    "workers_list": workers_list,
                    "last_share": data.get("lastHash", 0),
                    "valid_shares": valid_shares,
                    "invalid_shares": data.get("invalidShares", 0),
                    "total_hashes": total_hashes,
                    "status": "online"
                }
        except requests.exceptions.RequestException as e:
            logger.warning(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(5)
            else:
                logger.error(f"All retry attempts failed for SupportXMR")
                import traceback
                logger.error(traceback.format_exc())
                return {"pool": "SupportXMR", "status": "error", "error": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"pool": "SupportXMR", "status": "error", "error": str(e)}

    return {"pool": "SupportXMR", "status": "offline"}

def get_supportxmr_stats():
    """Wrapper for backward compatibility"""
    return get_supportxmr_stats_with_retry()

def get_minexmr_stats():
    # MineXMR closed in 2022 - skipping this pool
    return {"pool": "MineXMR", "status": "offline", "error": "Pool closed in 2022"}

def get_nanopool_stats():
    try:
        logger.info("Fetching Nanopool stats")
        url = f"https://api.nanopool.org/v1/xmr/user/{WALLET}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        if response.status_code == 200:
            data = response.json()
            if data.get("status"):
                user_data = data.get("data", {})
                logger.info("Successfully fetched Nanopool stats")
                return {
                    "pool": "Nanopool",
                    "hashrate": user_data.get("hashrate", 0),
                    "balance": user_data.get("balance", 0),
                    "paid": user_data.get("paid", 0),
                    "workers": len(user_data.get("workers", [])),
                    "status": "online"
                }
            else:
                # Account not found on this pool
                logger.info("Account not found on Nanopool")
                return {"pool": "Nanopool", "status": "offline", "error": "Account not found"}
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to fetch Nanopool stats: {e}")
        return {"pool": "Nanopool", "status": "error", "error": str(e)}
    except Exception as e:
        logger.error(f"Unexpected error fetching Nanopool stats: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {"pool": "Nanopool", "status": "error", "error": str(e)}
    return {"pool": "Nanopool", "status": "offline"}

def format_hashrate(h):
    if h >= 1000000:
        return f"{h/1000000:.2f} MH/s"
    elif h >= 1000:
        return f"{h/1000:.2f} KH/s"
    else:
        return f"{h:.2f} H/s"

def format_xmr(amount):
    return f"{amount:.8f} XMR"

def get_xmr_price():
    """Get current XMR price from CoinGecko API"""
    try:
        logger.info("Fetching current XMR price from CoinGecko")
        response = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={
                "ids": "monero",
                "vs_currencies": "usd"
            },
            timeout=360
        )
        response.raise_for_status()
        price = response.json()['monero']['usd']
        logger.info(f"Current XMR price: ${price}")
        return price
    except Exception as e:
        logger.warning(f"Failed to fetch XMR price: {e}, using fallback price")
        return 155  # Fallback price

def format_usd(xmr_amount, xmr_price=None):
    if xmr_price is None:
        xmr_price = get_xmr_price()
    return f"${xmr_amount * xmr_price:.4f} USD"

def get_network_info():
    """Get Monero network information"""
    try:
        logger.info("Fetching Monero network info")
        response = requests.get(
            "https://moneroblocks.info/api/get_stats",
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        network_info = {
            'difficulty': data.get('difficulty', 0),
            'height': data.get('height', 0),
            'reward': data.get('reward', 0) / 1e12  # Convert from atomic units
        }
        logger.info(f"Network difficulty: {network_info['difficulty']}, Block reward: {network_info['reward']:.4f} XMR")
        return network_info
    except Exception as e:
        logger.warning(f"Failed to fetch network info: {e}")
        return None

def calculate_earnings(hashrate):
    """Calculate estimated earnings with accurate network data"""
    network_info = get_network_info()
    if network_info and network_info['difficulty'] > 0:
        # More accurate calculation
        blocks_per_day = 720  # Approximately 2 minutes per block
        network_hashrate = network_info['difficulty'] / 120  # 2 min block time

        share_of_network = hashrate / network_hashrate if network_hashrate > 0 else 0
        xmr_per_day = share_of_network * blocks_per_day * network_info['reward']

        logger.info(f"Estimated earnings: {xmr_per_day:.8f} XMR/day (Network hashrate: {network_hashrate:.2f} H/s)")
        return xmr_per_day
    else:
        # Fallback to simple calculation
        xmr_per_day = (hashrate * 86400) / 1500000000000
        logger.info(f"Estimated earnings (fallback): {xmr_per_day:.8f} XMR/day")
        return xmr_per_day

def calculate_time_to_payout(balance, hashrate, threshold):
    if hashrate == 0:
        return "∞"
    remaining = threshold - balance
    if remaining <= 0:
        return "Ready!"
    xmr_per_day = calculate_earnings(hashrate)
    days = remaining / xmr_per_day if xmr_per_day > 0 else 999999
    if days < 1:
        return f"{days*24:.1f} hours"
    elif days < 30:
        return f"{days:.1f} days"
    else:
        return f"{days/30:.1f} months"

def print_header():
    print("=" * 100)
    print(f"{'XMR MINING MONITOR':^100}")
    print(f"{'Wallet: ' + WALLET[:20] + '...' + WALLET[-20:]:^100}")
    print(f"{'Updated: ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S'):^100}")
    print("=" * 100)

def print_pool_stats(stats, xmr_price=155):
    pool = stats.get("pool", "Unknown")
    status = stats.get("status", "unknown")
    
    print(f"\n┌─ {pool} Pool " + "─" * (90 - len(pool)))
    
    if status == "online":
        print(f"│ Status:          ✅ ONLINE")
        print(f"│ Hashrate:        {format_hashrate(stats.get('hashrate', 0))}")
        print(f"│ Balance:         {format_xmr(stats.get('balance', 0))} ({format_usd(stats.get('balance', 0), xmr_price)})")
        print(f"│ Total Paid:      {format_xmr(stats.get('paid', 0))} ({format_usd(stats.get('paid', 0), xmr_price)})")

        # Show worker count
        workers_count = stats.get('workers', 0)
        print(f"│ Active Workers:  {workers_count}")

        # Show individual workers if available
        workers_list = stats.get('workers_list', [])
        if workers_list:
            print(f"│ Worker Details:")
            for worker in workers_list:
                worker_id = worker.get('id', 'unknown')
                worker_hash = worker.get('hashrate', 0)
                print(f"│   • {worker_id}: {format_hashrate(worker_hash)}")

        if 'valid_shares' in stats:
            valid = stats.get('valid_shares', 0)
            invalid = stats.get('invalid_shares', 0)
            total = valid + invalid
            if total > 0:
                acceptance = (valid / total) * 100
                print(f"│ Valid Shares:    {valid} ({acceptance:.2f}% acceptance)")
                print(f"│ Invalid Shares:  {invalid}")

        # Show total hashes if available
        if 'total_hashes' in stats:
            total_hashes = stats.get('total_hashes', 0)
            print(f"│ Total Hashes:    {total_hashes:,}")

        threshold = 0.1 if pool == "SupportXMR" else (0.004 if pool == "MineXMR" else 0.3)
        progress = (stats.get('balance', 0) / threshold) * 100
        print(f"│ Threshold:       {format_xmr(threshold)} ({progress:.2f}% reached)")
        print(f"│ Time to Payout:  {calculate_time_to_payout(stats.get('balance', 0), stats.get('hashrate', 0), threshold)}")
        
    elif status == "error":
        print(f"│ Status:          ⚠️  ERROR")
        print(f"│ Error:           {stats.get('error', 'Unknown error')}")
    else:
        print(f"│ Status:          ⭕ OFFLINE")
        if 'error' in stats:
            print(f"│ Reason:          {stats.get('error', '')}")

    print("└" + "─" * 99)

def print_summary(all_stats, xmr_price=155):
    total_hashrate = sum(s.get('hashrate', 0) for s in all_stats if s.get('status') == 'online')
    total_balance = sum(s.get('balance', 0) for s in all_stats if s.get('status') == 'online')
    total_paid = sum(s.get('paid', 0) for s in all_stats if s.get('status') == 'online')
    total_workers = sum(s.get('workers', 0) for s in all_stats if s.get('status') == 'online')
    active_pools = sum(1 for s in all_stats if s.get('status') == 'online')
    
    print("\n" + "=" * 100)
    print(f"{'SUMMARY':^100}")
    print("=" * 100)
    print(f"│ Total Hashrate:     {format_hashrate(total_hashrate)}")
    print(f"│ Total Balance:      {format_xmr(total_balance)} ({format_usd(total_balance, xmr_price)})")
    print(f"│ Total Paid:         {format_xmr(total_paid)} ({format_usd(total_paid, xmr_price)})")
    print(f"│ Total Workers:      {total_workers}")
    print(f"│ Pool:               SupportXMR")
    print(f"│ Total Earnings:     {format_xmr(total_balance + total_paid)} ({format_usd(total_balance + total_paid, xmr_price)})")
    print("=" * 100)

def print_estimated_earnings(total_hashrate, xmr_price=155):
    if total_hashrate == 0:
        return
    
    xmr_per_day = calculate_earnings(total_hashrate)
    
    print(f"\n{'ESTIMATED EARNINGS':^100}")
    print("─" * 100)
    print(f"│ Current XMR Price: ${xmr_price:.2f}")
    print(f"│ Per Day:      {format_xmr(xmr_per_day)} ({format_usd(xmr_per_day, xmr_price)})")
    print(f"│ Per Week:     {format_xmr(xmr_per_day * 7)} ({format_usd(xmr_per_day * 7, xmr_price)})")
    print(f"│ Per Month:    {format_xmr(xmr_per_day * 30)} ({format_usd(xmr_per_day * 30, xmr_price)})")
    print(f"│ Per Year:     {format_xmr(xmr_per_day * 365)} ({format_usd(xmr_per_day * 365, xmr_price)})")
    print("─" * 100)

def main():
    logger.info("Starting XMR Mining Monitor")
    print("🚀 Starting XMR Mining Monitor...")
    print(f"📊 Checking every {CHECK_INTERVAL} seconds")
    print(f"💼 Wallet: {WALLET[:20]}...{WALLET[-20:]}\n")
    
    iteration = 0
    
    while True:
        try:
            iteration += 1
            logger.info(f"Starting iteration #{iteration}")
            clear_screen()
            
            print_header()

            # Fetch XMR price once per iteration
            current_xmr_price = get_xmr_price()

            print("\n🔍 Fetching data from SupportXMR pool...")
            supportxmr = get_supportxmr_stats()
            print(f"   Status: {supportxmr.get('status', 'unknown')}")
            if supportxmr.get('status') == 'error':
                print(f"   Error: {supportxmr.get('error', 'Unknown')}")
                logger.error(f"SupportXMR error: {supportxmr.get('error', 'Unknown')}")
            elif supportxmr.get('status') == 'online':
                print(f"   Hashrate: {supportxmr.get('hashrate', 0):.2f} H/s")

                # Show worker details in summary
                workers_list = supportxmr.get('workers_list', [])
                if workers_list:
                    print(f"\n   Worker Details:")
                    total_hash = 0
                    for worker in workers_list:
                        worker_id = worker.get('id', 'unknown')
                        worker_hash = worker.get('hashrate', 0)
                        total_hash += worker_hash
                        print(f"     • {worker_id}: {worker_hash:.2f} H/s")
                    print(f"\n   Total Hashrate: {total_hash:.2f} H/s")

            all_stats = [supportxmr]

            for stats in all_stats:
                print_pool_stats(stats, current_xmr_price)
            
            print_summary(all_stats, current_xmr_price)
            
            total_hashrate = sum(s.get('hashrate', 0) for s in all_stats if s.get('status') == 'online')
            print_estimated_earnings(total_hashrate, current_xmr_price)
            
            print(f"\n{'⏰ Next update in ' + str(CHECK_INTERVAL) + ' seconds... (Iteration #' + str(iteration) + ')':^100}")
            print(f"{'Press Ctrl+C to stop':^100}\n")
            
            logger.info(f"Iteration #{iteration} completed successfully")
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
            print("\n\n👋 Monitoring stopped by user.")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            print(f"\n❌ Error in main loop: {e}")
            import traceback
            logger.error(traceback.format_exc())
            traceback.print_exc()
            time.sleep(30)

if __name__ == "__main__":
    main()
