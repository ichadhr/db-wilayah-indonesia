# Codebase Improvement Roadmap

## High Priority (Phase 1: COMPLETED)
### 1. Refactor main.py into smaller modules ✅ COMPLETED
- [x] Create `src/pipeline/` directory structure
- [x] Move PipelineOrchestrator to orchestrator.py
- [x] Extract configuration to config.py
- [x] Split pipeline steps into separate files
- [x] Update imports and test functionality

### 2. Externalize configuration ✅ COMPLETED
- [x] Create `src/config/` directory
- [x] Define configuration classes with pydantic-settings
- [x] Move hardcoded constants to config files
- [x] Add environment variable support
- [x] Update main.py to use new configuration system

**Phase 1 Summary:**
- Successfully refactored main.py into modular pipeline components
- Configuration externalized using pydantic-settings with environment variable support
- All Phase 1 improvements completed successfully

### 3. Implement Luigi pipeline orchestration
- [ ] Review existing luigi_implementation.md design
- [ ] Create Luigi tasks for each pipeline step
- [ ] Implement dependency management between tasks
- [ ] Add Luigi configuration and central scheduler
- [ ] Migrate existing pipeline logic to Luigi framework
- [ ] Test pipeline execution with Luigi

## Medium Priority (Phase 2: 1-2 weeks)
### 4. Standardize error handling (5-6 weeks)
- [ ] **Phase 1: Core Extractors (1-2 weeks)**
  - [ ] Integrate structured errors in `pdf_table.py` - Table extraction errors
  - [ ] Integrate structured errors in `pdf_structure.py` - PDF structure analysis errors
  - [ ] Update `main.py` - Batch processing error handling
- [ ] **Phase 2: Specialized Modules (1 week)**
  - [ ] Integrate structured errors in `kode_wilayah_ocr.py` - OCR processing errors
  - [ ] Integrate structured errors in `scrapers/singkatan.py` - Image download errors
- [ ] **Phase 3: Utilities (1 week)**
  - [ ] Integrate structured errors in `utils/` modules - Path, converter, structure utilities
- [ ] **Testing (2 weeks)**
  - [ ] Integration tests for error propagation
  - [ ] Log analysis and error recovery validation
- [ ] Add structured logging with JSON format option
- [ ] Implement error correlation IDs

### 5. Extract common validation patterns
- [ ] Create `src/validators/` directory
- [ ] Move duplicated validation logic to shared utilities
- [ ] Create validation decorators
- [ ] Update modules to use centralized validators

### 6. Implement performance monitoring
- [ ] Create `src/monitoring/` directory
- [ ] Add metrics collection classes
- [ ] Track execution times and resource usage
- [ ] Export metrics to JSON/CSV

### 7. Implement parquet file merger
- [ ] Create `ParquetFileMerger` class in `src/utils/data_merger.py`
- [ ] Implement `merge_province_parquet_files()` method for generic merging
- [ ] Implement convenience methods for:
  - [ ] `merge_kabupaten_kota_index()` - kabupaten/kota index files
  - [ ] `merge_kecamatan_index()` - kecamatan index files
  - [ ] `merge_kabupaten_kota_detail()` - kabupaten/kota detail files
- [ ] Add province column enrichment during merge
- [ ] Integrate post-processing calls in main pipeline after batch processing
- [ ] Add error handling and logging for merge operations
- [ ] Test with actual province parquet files

## Low Priority (Phase 3: 1 week)
### 7. Code style and naming consistency
- [ ] Apply black formatter and isort
- [ ] Standardize naming conventions
- [ ] Add comprehensive docstrings
- [ ] Ensure PEP 8 compliance

### 8. Improve type safety
- [ ] Audit and replace Any types
- [ ] Use TypedDict for complex structures
- [ ] Add specific type annotations
- [ ] Enable strict type checking

### 9. Enhanced logging configuration
- [ ] Add configurable verbosity levels
- [ ] Implement multiple output formats
- [ ] Add log filtering by component
- [ ] Create separate log files for different modules

## Implementation Notes
- Each phase can be implemented incrementally
- Run full pipeline tests after each major change
- Update documentation as changes are made
- Consider backward compatibility for configuration