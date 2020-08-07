/*
MariaDB Data Transfer

Source Server         : Debian
Source Server Version : 100122
Source Host           : master:3306
Source Database       : wilayah

Target Server Type    : MariaDB
Target Server Version : 100122
File Encoding         : 65001

Date: 2017-03-27 00:00:00
*/

SET FOREIGN_KEY_CHECKS=0;

-- ----------------------------
-- Table structure for tbl_kabkot
-- ----------------------------
DROP TABLE IF EXISTS `tbl_kabkot`;
CREATE TABLE `tbl_kabkot` (
  `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `provinsi_id` int(11) unsigned NOT NULL,
  `kabupaten_kota` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `ibukota` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `k_bsni` char(3) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `kabkot` (`kabupaten_kota`) USING BTREE,
  KEY `fk_provs_kabkots_idx` (`provinsi_id`),
  KEY `kbsni` (`k_bsni`) USING BTREE,
  CONSTRAINT `fk_provs_kabkots_idx` FOREIGN KEY (`provinsi_id`) REFERENCES `tbl_provinsi` (`id`) ON DELETE NO ACTION ON UPDATE NO ACTION
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;



-- ----------------------------
-- Table structure for tbl_kecamatan
-- ----------------------------
DROP TABLE IF EXISTS `tbl_kecamatan`;
CREATE TABLE `tbl_kecamatan` (
  `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `kabkot_id` int(11) unsigned NOT NULL,
  `kecamatan` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_kabkots_kecs_idx` (`kabkot_id`),
  KEY `kecamatan` (`kecamatan`) USING BTREE,
  CONSTRAINT `fk_kabkots_kecs_idx` FOREIGN KEY (`kabkot_id`) REFERENCES `tbl_kabkot` (`id`) ON DELETE NO ACTION ON UPDATE NO ACTION
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;



-- ----------------------------
-- Table structure for tbl_kelurahan
-- ----------------------------
DROP TABLE IF EXISTS `tbl_kelurahan`;
CREATE TABLE `tbl_kelurahan` (
  `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `kecamatan_id` int(11) unsigned NOT NULL,
  `kelurahan` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `kd_pos` char(5) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_kecs_kels_idx` (`kecamatan_id`),
  KEY `kelurahan` (`kelurahan`) USING BTREE,
  KEY `kdpos` (`kd_pos`) USING BTREE,
  CONSTRAINT `fk_kecs_kels_idx` FOREIGN KEY (`kecamatan_id`) REFERENCES `tbl_kecamatan` (`id`) ON DELETE NO ACTION ON UPDATE NO ACTION
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;



-- ----------------------------
-- Table structure for tbl_provinsi
-- ----------------------------
DROP TABLE IF EXISTS `tbl_provinsi`;
CREATE TABLE `tbl_provinsi` (
  `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `provinsi` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `ibukota` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `p_bsni` char(5) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `provinsi` (`provinsi`) USING BTREE,
  KEY  `ibukota_provinsi` (`ibukota`) USING BTREE,
  KEY `pbsni` (`p_bsni`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS=1;