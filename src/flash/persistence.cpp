/**
 * Flash Persistence Layer
 *
 * Handles wear-leveling and safe storage of weight shards.
 * TLSR8258 flash has ~100K erase cycles per sector.
 */

#include "neuron_config.h"
#include "weight_shard.h"

extern "C" {
#include "drivers.h"
}

namespace planetary {

// Flash geometry
constexpr uint32_t FLASH_SECTOR_SIZE = 4096;
constexpr uint32_t FLASH_WEIGHT_BASE = 0x40000;
constexpr uint8_t  SECTORS_PER_SHARD = 2;  // Double-buffer for wear leveling

// Sector header for wear tracking
struct SectorHeader {
    uint32_t magic;           // 0xPLANET01
    uint32_t write_count;     // Erase cycles
    uint16_t shard_id;
    uint16_t flags;           // 0x01 = valid, 0x02 = active
} __attribute__((packed));

constexpr uint32_t SECTOR_MAGIC = 0x504C4E01;  // "PLN\x01"

class FlashPersistence {
public:
    // Find the active sector for a shard (wear-leveled)
    static uint32_t findActiveSector(uint8_t shard_id) {
        uint32_t base = FLASH_WEIGHT_BASE + shard_id * SECTORS_PER_SHARD * FLASH_SECTOR_SIZE;

        SectorHeader hdr0, hdr1;
        flash_read_page(base, sizeof(hdr0), reinterpret_cast<uint8_t*>(&hdr0));
        flash_read_page(base + FLASH_SECTOR_SIZE, sizeof(hdr1), reinterpret_cast<uint8_t*>(&hdr1));

        bool valid0 = (hdr0.magic == SECTOR_MAGIC) && (hdr0.flags & 0x01);
        bool valid1 = (hdr1.magic == SECTOR_MAGIC) && (hdr1.flags & 0x01);

        if (!valid0 && !valid1) return 0;  // Neither valid
        if (valid0 && !valid1) return base;
        if (!valid0 && valid1) return base + FLASH_SECTOR_SIZE;

        // Both valid - use the one with active flag, or higher write count
        if (hdr0.flags & 0x02) return base;
        if (hdr1.flags & 0x02) return base + FLASH_SECTOR_SIZE;

        return (hdr0.write_count >= hdr1.write_count) ? base : base + FLASH_SECTOR_SIZE;
    }

    // Write shard with wear leveling
    static bool writeShard(const WeightShard& shard) {
        uint8_t shard_id = shard.header.shard_id;
        uint32_t base = FLASH_WEIGHT_BASE + shard_id * SECTORS_PER_SHARD * FLASH_SECTOR_SIZE;

        // Find current active sector
        uint32_t active = findActiveSector(shard_id);

        // Write to the OTHER sector (ping-pong)
        uint32_t target = (active == base) ? (base + FLASH_SECTOR_SIZE) : base;

        // Read old header for write count
        SectorHeader old_hdr;
        flash_read_page(target, sizeof(old_hdr), reinterpret_cast<uint8_t*>(&old_hdr));
        uint32_t write_count = (old_hdr.magic == SECTOR_MAGIC) ? old_hdr.write_count + 1 : 1;

        // Erase target sector
        flash_erase_sector(target);

        // Write new header
        SectorHeader new_hdr = {
            .magic = SECTOR_MAGIC,
            .write_count = write_count,
            .shard_id = shard_id,
            .flags = 0x03  // Valid + Active
        };
        flash_write_page(target, sizeof(new_hdr), reinterpret_cast<const uint8_t*>(&new_hdr));

        // Write shard data after header
        flash_write_page(target + sizeof(SectorHeader), sizeof(WeightShard),
                        reinterpret_cast<const uint8_t*>(&shard));

        // Mark old sector as inactive (if it was valid)
        if (active != 0 && active != target) {
            SectorHeader inactive = {
                .magic = SECTOR_MAGIC,
                .write_count = 0,
                .shard_id = shard_id,
                .flags = 0x01  // Valid but not active
            };
            // Note: This just marks first byte, doesn't require erase
            flash_write_page(active, sizeof(inactive), reinterpret_cast<const uint8_t*>(&inactive));
        }

        return true;
    }

    // Read shard from flash
    static bool readShard(uint8_t shard_id, WeightShard& shard) {
        uint32_t sector = findActiveSector(shard_id);
        if (sector == 0) return false;

        flash_read_page(sector + sizeof(SectorHeader), sizeof(WeightShard),
                       reinterpret_cast<uint8_t*>(&shard));

        return shard.verifyChecksum();
    }

    // Get wear stats for monitoring
    static uint32_t getWearCount(uint8_t shard_id) {
        uint32_t sector = findActiveSector(shard_id);
        if (sector == 0) return 0;

        SectorHeader hdr;
        flash_read_page(sector, sizeof(hdr), reinterpret_cast<uint8_t*>(&hdr));
        return hdr.write_count;
    }
};

}  // namespace planetary
