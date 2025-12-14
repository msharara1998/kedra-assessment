#!/bin/bash
# Helper script to manage services and run pipeline tests

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

function print_header() {
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}$1${NC}"
    echo -e "${GREEN}========================================${NC}"
}

function print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

function print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

function print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

function check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        print_error "Docker daemon is not running"
        exit 1
    fi
    
    print_info "Docker is running"
}

function start_services() {
    print_header "Starting Services"
    
    check_docker
    
    print_info "Starting MongoDB and MinIO..."
    docker-compose up -d
    
    print_info "Waiting for services to be ready..."
    sleep 5
    
    # Check if services are running
    if docker-compose ps | grep -q "Up"; then
        print_info "✓ Services are running"
        docker-compose ps
    else
        print_error "Services failed to start"
        docker-compose logs
        exit 1
    fi
}

function stop_services() {
    print_header "Stopping Services"
    
    docker-compose down
    print_info "✓ Services stopped"
}

function status_services() {
    print_header "Service Status"
    
    docker-compose ps
}

function run_test() {
    print_header "Running Pipeline Test"
    
    # Check if .env exists
    if [ ! -f .env ]; then
        print_warning ".env file not found, creating from template..."
        cp .env.template .env
        print_info "✓ Created .env file"
    fi
    
    # Check if services are running
    if ! docker-compose ps | grep -q "Up"; then
        print_warning "Services are not running, starting them..."
        start_services
    fi
    
    print_info "Running test_pipeline.py..."
    python test_pipeline.py
}

function view_results() {
    print_header "Viewing Results"
    
    print_info "MongoDB Records:"
    docker exec -it wr-mongo mongosh workplace_relations --quiet --eval "
        print('Total records:', db.records.countDocuments({}));
        print('\\nStatus breakdown:');
        db.records.aggregate([
            { \$group: { _id: '\$status', count: { \$sum: 1 } } }
        ]).forEach(doc => print('  -', doc._id + ':', doc.count));
        print('\\nRecent records:');
        db.records.find().sort({created_at: -1}).limit(3).forEach(doc => {
            print('\\n  ID:', doc.identifier);
            print('    Status:', doc.status);
            print('    MIME:', doc.mime_type);
            print('    File:', doc.file_path);
            print('    Hash:', doc.file_hash ? doc.file_hash.substring(0, 16) + '...' : 'N/A');
        });
    "
    
    print_info "\nMinIO Console: http://localhost:9001"
    print_info "  Username: minioadmin"
    print_info "  Password: minioadmin"
}

function clean_data() {
    print_header "Cleaning Test Data"
    
    read -p "Are you sure you want to delete all test data? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "Clearing MongoDB records..."
        docker exec -it wr-mongo mongosh workplace_relations --quiet --eval "
            db.records.deleteMany({});
            print('Deleted', db.records.countDocuments({}), 'records');
        "
        
        print_warning "To clear MinIO data, restart containers with: docker-compose down -v && docker-compose up -d"
        print_info "✓ MongoDB data cleared"
    else
        print_info "Cancelled"
    fi
}

function show_help() {
    cat << EOF
MetadataPipeline Test Helper

Usage: $0 [command]

Commands:
    start       Start MongoDB and MinIO services
    stop        Stop services
    status      Show service status
    test        Run pipeline test
    results     View test results from MongoDB
    clean       Clean test data (interactive)
    help        Show this help message

Examples:
    $0 start          # Start services
    $0 test           # Run test (auto-starts services if needed)
    $0 results        # View results in MongoDB
    $0 clean          # Clean test data
    $0 stop           # Stop services

EOF
}

# Main script
case "${1:-}" in
    start)
        start_services
        ;;
    stop)
        stop_services
        ;;
    status)
        status_services
        ;;
    test)
        run_test
        ;;
    results)
        view_results
        ;;
    clean)
        clean_data
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        show_help
        exit 1
        ;;
esac

exit 0
