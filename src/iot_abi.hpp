#pragma once
// Reconstructed from matching IOT_LIB.pdb, GUID 1f279e81-eb18-4bc7-9ec6-537ae4073c17 age 2.
// Initializer and message prefix used for reading state and white-light control.
#include <cstdint>
#include <cstddef>
#include <memory>
#include <string>
#if !defined(_MSC_VER) || !defined(_M_X64)
#error Requires MSVC-compatible x64 ABI with Microsoft STL
#endif
static_assert(sizeof(std::string) == 32, "Incompatible string ABI");
static_assert(sizeof(std::shared_ptr<void>) == 16, "Incompatible shared_ptr ABI");
namespace iotvideo {
enum class DeviceType : int { TID=1, DID=2, THIRD_ID=3 };
enum class IoTLinkState : int { IDLE=-10, UNREGISTERING=-1, REGISTERING=0, ONLINE=1, OFFLINE=2 };
struct InitializerParams {
    std::uint64_t access_id = 0;
    std::string access_token;
    std::string iv_host;
    DeviceType device_type = DeviceType::TID;
    short app_sys_lang = 0;
    std::uint32_t p2p_port_type = 0;
    int log_level = 4;
};
static_assert(sizeof(InitializerParams)==88);
static_assert(offsetof(InitializerParams,access_token)==8);
static_assert(offsetof(InitializerParams,iv_host)==40);
static_assert(offsetof(InitializerParams,device_type)==72);
static_assert(offsetof(InitializerParams,app_sys_lang)==76);
static_assert(offsetof(InitializerParams,p2p_port_type)==80);
static_assert(offsetof(InitializerParams,log_level)==84);
class IIoTVideoInitializer {
public:
    class Listener;
    virtual void register_p2p(InitializerParams) = 0;
    virtual void unregister_p2p(bool) = 0;
    virtual void set_state_listener(std::shared_ptr<Listener>) = 0;
    virtual IoTLinkState link_state() = 0;
    virtual void update_access_token(std::string) = 0;
    // No virtual destructor in this interface: adding one changes the vtable.
};
static_assert(sizeof(IIoTVideoInitializer)==8);
using InitializerFactory = std::shared_ptr<IIoTVideoInitializer> (*)();
inline constexpr char initializer_export[] =
 "?instance_ptr@IIoTVideoInitializer@iotvideo@@SA?AV?$shared_ptr@VIIoTVideoInitializer@iotvideo@@@std@@XZ";
}

#include <functional>
#include <vector>
namespace gwbase {
struct Error {
    std::string domain;
    int cat;
    std::string cat_desc;
    int code;
    std::string code_desc;
    std::string user_info;
};
static_assert(sizeof(Error)==144);
static_assert(offsetof(Error,code)==72);
}
namespace iotvideo {
struct ITaskScheduler {
    using Task=std::function<void()>;
    std::function<void(Task)> schedule_on;
};
struct IMessageCallback : ITaskScheduler {
    enum Result : int { CONTINUE=0, FINISHED=1 };
    std::function<Result(unsigned int)> on_send;
    std::function<Result(std::vector<unsigned char>, std::int64_t)> on_ack;
    std::function<Result(std::vector<unsigned char>, std::int64_t)> on_recv_data;
    std::function<Result(std::shared_ptr<gwbase::Error>)> on_error;
};
static_assert(sizeof(std::vector<unsigned char>)==24);
static_assert(sizeof(std::function<void()>)==64);
static_assert(sizeof(ITaskScheduler)==64);
static_assert(sizeof(IMessageCallback)==320);
// PDB records 0x6934 and 0x6b26. No virtual destructor in either callback class.
#ifdef __clang__
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Winvalid-offsetof"
#endif
// MSVC accepts offsetof for this inherited, non-standard-layout ABI record.
static_assert(offsetof(IMessageCallback,on_send)==64);
static_assert(offsetof(IMessageCallback,on_ack)==128);
static_assert(offsetof(IMessageCallback,on_recv_data)==192);
static_assert(offsetof(IMessageCallback,on_error)==256);
#ifdef __clang__
#pragma clang diagnostic pop
#endif
class IMessageMgr {
public:
    // Prefix of the real vtable: read at byte offset 8, send at offset 48.
    virtual void write_property_of_device(std::string,std::string,std::string,std::int64_t,std::shared_ptr<IMessageCallback>)=0;
    virtual void read_property_of_device(std::string,std::string,std::int64_t,std::shared_ptr<IMessageCallback>)=0;
    virtual void take_action_of_device(std::string,std::string,std::string,std::int64_t,std::shared_ptr<IMessageCallback>)=0;
    virtual void add_property_of_device(std::string,std::string,std::string,std::int64_t,std::shared_ptr<IMessageCallback>)=0;
    virtual void delete_property_of_device(std::string,std::string,std::int64_t,std::shared_ptr<IMessageCallback>)=0;
    virtual void refresh_property_of_device(std::string,std::string)=0;
    virtual void send_msg_to_device(std::string,std::vector<unsigned char>,std::int64_t,bool,bool,unsigned int,std::shared_ptr<IMessageCallback>)=0;
};
using MessageFactory=std::shared_ptr<IMessageMgr> (*)();
inline constexpr char message_export[]="?shared_mgr@IMessageMgr@iotvideo@@SA?AV?$shared_ptr@VIMessageMgr@iotvideo@@@std@@XZ";
inline constexpr char online_property[]="ProReadonly._online";
}
